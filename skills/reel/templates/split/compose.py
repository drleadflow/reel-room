#!/usr/bin/env python3
"""compose.py <project> [--safe-overlay] [--no-measure] [--json]
Lint the result from the project folder with exactly:  npx --yes hyperframes@0.8.34 lint   (0 errors required;
render.py does this for you).

edl.json + segments.json + words.json + work/facepos.json (+ work/facetrack.json) + project.json + brand.json
  -> index.html (HyperFrames composition, one paused GSAP timeline) + layout_boxes.json (for qa.py / styleqa.py).

Layouts per segment (`mode`) or project beat (`layout`): split | full | card | stage | media  (see layouts.py).
Beat spec (edl segment `top`, or project.json `beats` for mid-segment changes):
  top: {"insert": "number", "args": {"n": 1, "title": "Blood work"}} | [item, item] | "same" (keep previous beat)
  beats: [{"at_src": {"seg": "n5a", "t": 268.5} | "at": 69.0 | "at_word": "someone", "seg": "n5a",
           "layout": "split", "insert": "video", "args": {...}, "until_word": "..."|"until": t|"dur": s}]
  `top` on a FULL segment = full-frame overlay items placed above the head box (overlay.py).
  edl segment "punch": 1.15 = css punch-in around the face on a full segment (a framing change on a jump cut);
  on a card segment it multiplies card.scale. "punch_at": [x, y] puts the face centre there on a punched full segment.
Persistent overlays (whole video or a range, e.g. the list-stack list): project.json
  "overlays": [{"insert": "list_stack", "args": {...}, "from": 0, "until": null}]
Styles: project.json "style": "<id>" loads templates/<id>/style.py (extra inserts, css, fonts, caption defaults).
Captions: project.json "captions": {"mode": "pill"|"word", "full_style": "pill|shadow|scrim", "max_words": 3,
  "hold_gap": 0.4 (a caption stays up until the next word when the pause is shorter than this)}.
"""
import importlib.util
import json
import os
import shutil
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import captions as caps_  # noqa: E402
import deck  # noqa: E402
import deck_inserts  # noqa: E402
import facetrack  # noqa: E402
import feed  # noqa: E402
import inserts  # noqa: E402
import inserts_media as media  # noqa: E402
import kallaway  # noqa: E402
import layouts as lay  # noqa: E402
import measure  # noqa: E402
import motionlayer  # noqa: E402
import overlay as ovl_  # noqa: E402
import page  # noqa: E402
import presets  # noqa: E402
import theme  # noqa: E402
import timeline as tl_  # noqa: E402
from ctx import Ctx, esc  # noqa: E402
from report import KIND, beat_sig, frame_duration, jump_cut_warnings, pip_mask, qa_beats  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.dirname(HERE)
GSAP_VER = "3.14.2"
GSAP_CDN = f"https://cdn.jsdelivr.net/npm/gsap@{GSAP_VER}/dist/gsap.min.js"
FACE_OFFSET = 350   # px between the seam and the detected face centre in split (spec ~330; 350 matches the reference reels)
SEAM = lay.SEAM
LIB = {
    "hook_card": inserts.hook_card, "polaroids": inserts.polaroids, "number": inserts.number, "table": inserts.table,
    "calendar": inserts.calendar, "checklist": inserts.checklist, "two_path": inserts.two_path,
    "strike_pill": inserts.strike_pill, "cta": inserts.cta, "stat": inserts.stat,
    "image": media.image, "flip": media.flip, "video": media.video, "collage": media.collage,
    "name_card": ovl_.name_card, "chip": ovl_.chip,
}
ALIASES = {"hook": "hook_card", "polaroid": "polaroids", "polaroid_row": "polaroids", "number_card": "number",
           "data_table": "table", "calendar_grid": "calendar", "two_path_card": "two_path", "strike": "strike_pill",
           "cta_card": "cta", "broll": "video", "collage2x2": "collage", "before_after": "flip", "big_stat": "stat",
           "lower_third": "name_card"}


def jload(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    if default is None:
        raise SystemExit(f"missing {path}")
    return default


def load_style(style_id):
    """templates/<style_id>/style.py -> module (or None for the plain split deck)."""
    if not style_id or style_id in ("split", "split-deck"):
        return None
    path = os.path.join(TEMPLATES, style_id, "style.py")
    if not os.path.exists(path):
        print(f"  WARN style '{style_id}' has no templates/{style_id}/style.py; using split-deck")
        return None
    spec = importlib.util.spec_from_file_location(f"rr_style_{style_id.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_plan_inserts():
    """Inserts the plan compiler writes (engine/compile/kit_insert.py): "kit" (any rrkit piece) and "word_card".
    Loaded by path so engine/compile never lands on sys.path."""
    path = os.path.join(os.path.dirname(TEMPLATES), "engine", "compile", "kit_insert.py")
    if not os.path.exists(path):
        return {}
    spec = importlib.util.spec_from_file_location("rr_plan_inserts", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.INSERTS


def ensure_gsap(project):
    dest = os.path.join(project, "assets", "gsap.min.js")
    cache = os.path.join(theme.HOME, "cache", f"gsap-{GSAP_VER}.min.js")
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if not os.path.exists(cache):
        try:
            urllib.request.urlretrieve(GSAP_CDN, cache)
        except Exception:  # noqa: BLE001
            return GSAP_CDN
    shutil.copyfile(cache, dest)
    return "assets/gsap.min.js"


def beat_area(cx, b):
    """Vertical band (y0, y1) where a beat's inserts may sit."""
    lay_ = b["layout"]
    if lay_ == "split":
        return (220, 940)
    if lay_ == "card":
        return (220, cx.card["top"] - cx.card.get("caption_band", 120))
    if lay_ == "stage":
        return (220, cx.stage_bottom)
    if lay_ == "media":
        return (220, 1470)
    top = cx.head_top(b["t0"], b["t1"])
    return (220, max(260, top - cx.head_margin))


def render_items(cx, b, items, cls, lib):
    inner = []
    for it in items:
        name = it["insert"] if it["insert"] in lib else ALIASES.get(it["insert"], it["insert"])
        if name not in lib:
            raise SystemExit(f"unknown insert '{it['insert']}' in beat {b['id']} ({b['t0']:.2f}s). Known: {sorted(lib)}")
        args = dict(it.get("args", {}))
        args["_alone"] = len(items) == 1
        args["_area"] = beat_area(cx, b)
        args["_layout"] = b["layout"]
        inner.append(lib[name](cx, b, args))
    body = "".join(inner)
    if getattr(cx, "deck", False) and b["layout"] == "split":   # deck camera wrapper (deck.py); the beat keeps its clip
        body = f'<div class="dcam" id="{b["id"]}cam">{body}</div>'
    return f'<div class="beat {cls}" id="{b["id"]}" data-layout="{b["layout"]}">{body}</div>'


def render_beats(cx, beats, lib):
    html_parts = []
    for b in beats:
        if not b["items"]:
            continue
        cls = {"split": "", "full": "fullb", "card": "cardb", "stage": "stageb", "media": "mediab"}.get(b["layout"], "")
        html_parts.append(render_items(cx, b, b["items"], cls, lib))
        cx.set(f"#{b['id']}", b["t0"], {"autoAlpha": 1})
        cx.set(f"#{b['id']}", b["t1"], {"autoAlpha": 0})
    return "\n".join(html_parts)


def render_overlays(cx, specs, total, lib):
    """Persistent full-frame overlays (e.g. a list that fills in over the whole video)."""
    out = []
    whole = {"t0": 0.0, "t1": total, "id": "ovl"}
    for i, o in enumerate(specs or []):
        t0 = cx.when(o["from"], whole, 0) if o.get("from") else 0.0
        t1 = cx.when(o["until"], whole, total) if o.get("until") else total
        b = {"id": f"ov{i}", "t0": t0, "t1": min(t1, total), "layout": "overlay", "items": [o], "segs": []}
        name = o["insert"] if o["insert"] in lib else ALIASES.get(o["insert"], o["insert"])
        if name not in lib:
            raise SystemExit(f"unknown overlay insert '{o['insert']}'. Known: {sorted(lib)}")
        args = dict(o.get("args", {}))
        args["_area"] = (220, cx.head_top(b["t0"], b["t1"]) - cx.head_margin)
        args["_layout"] = "overlay"
        out.append(f'<div class="ovl" id="{b["id"]}">{lib[name](cx, b, args)}</div>')
        if t0 > 0:
            cx.set(f"#{b['id']}", t0, {"autoAlpha": 1})
            cx.init.append(f'gsap.set("#{b["id"]}", {{autoAlpha: 0}});')
        if t1 < total - 1e-3:
            cx.set(f"#{b['id']}", t1, {"autoAlpha": 0})
    return "\n".join(out)


def speaker_and_panel(cx, slices, facepos, face_offset, punches, targets=None):
    """Place the speaker per slice; switch panel / paper / card on the slice's first frame."""
    placement, prev = [], None
    for s in slices:
        fp = facepos.get(s["seg"])
        pl = lay.place(s["layout"], fp, face_offset, cx.card, punches.get(s["seg"], 1.0), cx.warn,
                       (targets or {}).get(s["seg"]))
        face = None
        if fp and pl["visible"]:
            skin, _ = lay.face_box(pl, fp["cx"], fp["cy"], fp["h"])
            face = {"cx": round(skin["x"] + skin["w"] / 2), "cy": round(skin["y"] + skin["h"] / 2),
                    "w": round(skin["w"]), "h": round(skin["h"])}
        placement.append({"t0": s["t0"], "t1": s["t1"], "seg": s["seg"], "layout": s["layout"], "dy": pl["dy"],
                          "dx": pl.get("dx", 0), "scale": pl["scale"], "ox": pl["ox"], "oy": pl["oy"],
                          "visible": pl["visible"], "clip": pl["clip"], "face": face})
        key = (s["layout"], json.dumps(pl, sort_keys=True))
        if key != prev:
            cx.set("#spmove", s["t0"], lay.transform_css(pl))
            cx.set("#sp", s["t0"], {"autoAlpha": 1 if pl["visible"] else 0,
                                    "clipPath": pl["clip"] or "inset(0px 0px 0px 0px)"})
            cx.set("#panel", s["t0"], {"autoAlpha": 1 if s["layout"] == "split" else 0})
            cx.set("#paper", s["t0"], {"autoAlpha": 1 if s["layout"] in ("card", "stage") else 0})
            cx.set("#cardsh", s["t0"], {"autoAlpha": 1 if s["layout"] == "card" else 0})
            prev = key
    return placement


FULL_CAP_MIN_TOP, FULL_CAP_MAX_TOP = 1250, 1366


def full_caption_top(cx, c):
    """Chest height, but always below the chin of THIS slice (from the per-frame track when present)."""
    chin = cx.chin(c["t0"], c["t1"])
    if chin is None:
        return FULL_CAP_MIN_TOP
    return round(min(max(FULL_CAP_MIN_TOP, chin + 26), FULL_CAP_MAX_TOP))


def render_captions(cx, chunks, full_style, cfg):
    mode = cfg.get("mode", "pill")
    out = []
    accent = cfg.get("accent")
    for i, c in enumerate(chunks):
        cid = f"c{i}"
        lay_ = c["layout"]
        if mode == "word":
            txt = caps_.word_text(c["text"], cfg.get("strip_punct", True))
            acc = caps_.is_accent(c["text"], accent, i)
            pill = lay_ in ("full", "media")
            cls = f"wcap l-{lay_}{' acc' if acc else ''}{' wpill' if pill else ''}"
            top = cx.word_cap_top(c, lay_)
            # the text colour goes into layout_boxes so qa legibility judges ink-on-paper words correctly
            col = "" if pill else cx.brand["colors"]["accent" if acc else "ink"]
            out.append(f'<div class="cap {cls}" id="{cid}" style="top:{top}px" {cx.box("caption", c["t0"], c["t1"], True)} '
                       f'data-style="{"pill" if pill else "word"}" data-color="{col}"><span class="pill" data-fit="{860 if pill else 960},40" '
                       f'data-fitpad="{56 if pill else 0}">{esc(txt)}</span></div>')
        else:
            full = lay_ != "split"
            style = full_style if full else "pill"
            if style == "pill":
                fit = 'data-fit="880,40" data-fitpad="56"' if full else 'data-fit="940,30" data-fitpad="48"'
            else:
                fit = 'data-fit="880,40" data-fitpad="0"' if style == "shadow" else 'data-fit="880,40" data-fitpad="140"'
            top = f' style="top:{full_caption_top(cx, c)}px"' if full else ""
            cls = f'{"full" if full else "split"}{" " + style if full and style != "pill" else ""}'
            out.append(f'<div class="cap {cls}" id="{cid}"{top} {cx.box("caption", c["t0"], c["t1"], True)} data-style="{style}">'
                       f'<span class="pill" {fit}>{caps_.pill_html(c["text"], cfg)}</span></div>')
        cx.set(f"#{cid}", c["t0"], {"autoAlpha": 1})
        cx.set(f"#{cid}", c["t1"], {"autoAlpha": 0})
    return "\n".join(out)


def default_word_cap_top(cx, c, layout):
    if layout == "card":
        return cx.card["top"] - cx.card.get("caption_band", 120) + 6
    if layout == "stage":
        return cx.stage_bottom + 20
    if layout == "split":
        return 990
    return full_caption_top(cx, c)


def layout_css(cx):
    c = cx.card
    return f"""
#paper{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:0;opacity:0;visibility:hidden;background:var(--paper,var(--bg))}}
#cardsh{{position:absolute;left:{c['inset']}px;top:{c['top']}px;width:{1080 - 2 * c['inset']}px;height:{1920 - c['top'] + 80}px;z-index:0;
  border-radius:{c['radius']}px;opacity:0;visibility:hidden;background:#000;box-shadow:var(--cardshadow,0 30px 70px rgba(0,0,0,.18),0 6px 18px rgba(0,0,0,.08))}}
.beat.fullb,.beat.stageb,.beat.mediab{{height:1920px;overflow:visible}}
.beat.cardb{{height:{c['top']}px}}
.ovl{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:6;pointer-events:none}}
"""


def compose(project, overlay=False, do_measure=True, out_name="index.html"):
    """overlay=True paints the safe-zone guide (kept as the historical keyword)."""
    project = os.path.abspath(project)
    pj = jload(os.path.join(project, "project.json"), {})
    style = load_style(pj.get("style"))
    sdef = getattr(style, "DEFAULTS", {}) if style else {}
    brand = theme.load_brand(project)
    for k, v in sdef.get("fonts", {}).items():
        brand["fonts"].setdefault(k, v)
    words = tl_.Words(jload(os.path.join(project, "words.json")))
    edl = jload(os.path.join(project, "edl.json"))
    pre_warn = []   # a preset (presets.py) fills in settings, camera per segment and the top-slot plan; explicit wins
    pj, edl = presets.apply(project, pj, edl, jload(os.path.join(project, "words.json")), warn=pre_warn.append)
    segs = tl_.load_segments(edl, jload(os.path.join(project, "segments.json")))
    punches = {e["id"]: float(e["punch"]) for e in edl if e.get("punch")}
    targets = {e["id"]: e["punch_at"] for e in edl if e.get("punch_at")}
    facepos = jload(os.path.join(project, "work", "facepos.json"), {})
    hook = pj.get("hook", {})
    cx = Ctx(brand, words, hook, project)
    for w in pre_warn:
        cx.warn(w)
    cx.segs = segs
    # motion v2 (engine/motion): level simple | polished (default) | showreel; "motion": false = legacy, no motion layer
    mcfg = None if pj.get("motion") is False else motionlayer.config(project, pj)
    cx.motion_cfg = mcfg
    # split-deck deck camera + motion inserts (deck.py); other styles opt in with motion.deck
    cx.deck = deck.enabled(style, pj, mcfg)
    cx.deck_focus, cx.deck_accents = [], []
    cx.card = lay.card_cfg({"card": {**sdef.get("card", {}), **pj.get("card", {})}})
    cx.stage_bottom = pj.get("stage", {}).get("bottom", sdef.get("stage_bottom", 1180))
    cx.head_margin = pj.get("head_margin", sdef.get("head_margin", 24))
    total = segs[-1]["t1"]
    frames = round(total * tl_.FPS)
    dur_str = frame_duration(frames)
    print(f"compose: {frames} frames @ {tl_.FPS} fps -> data-duration {dur_str}s (ceil({dur_str}*{tl_.FPS}) = {frames})")

    beats = tl_.build_beats(segs, pj.get("beats"), words, hook)
    slices = tl_.build_slices(segs, beats)
    face_offset = pj.get("split", {}).get("face_offset", FACE_OFFSET)
    cx.beats = beats
    placement = speaker_and_panel(cx, slices, facepos, face_offset, punches, targets)
    track = facetrack.load(project)
    if track is None:
        cx.warn("no work/facetrack.json (run facetrack.py); overlays use the per-segment facepos only")
    cx.attach_heads(placement, track, facepos, segs)

    lib = dict(LIB)
    if cx.deck:
        lib.update(deck_inserts.INSERTS)
    if pj.get("_preset"):   # preset inserts only with a preset (never shadow a stock insert name)
        clash = set(lib) & (set(feed.INSERTS) | set(kallaway.INSERTS))
        if clash:
            raise SystemExit(f"preset inserts clash with stock inserts: {sorted(clash)}")
        lib.update({**feed.INSERTS, **kallaway.INSERTS})
    lib.update(load_plan_inserts())
    if style and hasattr(style, "INSERTS"):
        lib.update(style.INSERTS)
    beats_html = render_beats(cx, beats, lib)
    ovl_html = render_overlays(cx, pj.get("overlays"), total, lib)

    cap_cfg = {**sdef.get("captions", {}), **brand.get("captions", {}), **pj.get("captions", {})}
    mode = cap_cfg.get("mode", "pill")
    cap_slices = presets.caption_slices(slices) if pj.get("_preset") else slices
    chunks = caps_.chunks(words, cap_slices, cap_cfg.get("max_words", 3), cap_cfg.get("max_chars", 26),
                          gap=cap_cfg.get("hold_gap", 0.4), mode=mode)
    full_style = cap_cfg.get("full_style", "pill")
    if full_style not in ("pill", "shadow", "scrim"):
        cx.warn(f"captions.full_style '{full_style}' unknown; using pill")
        full_style = "pill"
    if style and hasattr(style, "word_cap_top"):
        cx.word_cap_top = lambda c, l: style.word_cap_top(cx, c, l)  # noqa: E731
    else:
        cx.word_cap_top = lambda c, l: default_word_cap_top(cx, c, l)  # noqa: E731
    if cap_cfg.get("no_repeat", True):
        nh = caps_.hide_repeats(chunks, caps_.shown_text(beats_html + ovl_html), mode, cap_cfg.get("repeat_window", 2.0))
        if nh:
            print(f"  captions: {nh} chunk(s) hidden while the same words are on screen as type")
    caps_html = render_captions(cx, [c for c in chunks if not c.get("hidden")], full_style, cap_cfg)
    if mode != "word":
        for o in caps_.orphans(chunks):
            cx.warn(f"orphan caption chunk: '{o}'")

    for w in jump_cut_warnings(segs, beats, punches, cx.cut_marks):
        cx.warn(w)
    if style and hasattr(style, "stage"):  # optional style hook: stage camera / layer rigs, before the motion plan
        style.stage(cx, beats, placement, segs=segs, mcfg=mcfg, captions=[c for c in chunks if not c.get("hidden")])
    mv = None
    if mcfg:
        mv = motionlayer.build(project, cx, mcfg, placement=placement, facepos=facepos, beats=beats, edl=edl,
                               words=jload(os.path.join(project, "words.json")), chunks=chunks, cap_cfg=cap_cfg,
                               frames=frames, brand=brand, pj=pj)
        cx.tw.extend(mv["js"])
    first = placement[0]
    first_pl = {"x": first["dx"], "y": first["dy"], "scale": first["scale"], "transformOrigin": f"{first['ox']}px {first['oy']}px"}
    init_js = "\n".join([f'  gsap.set("#spmove", {json.dumps(first_pl)});',
                         f'  gsap.set("#sp", {{ autoAlpha: {1 if first["visible"] else 0}, clipPath: {json.dumps(first["clip"] or "inset(0px 0px 0px 0px)")} }});',
                         f'  gsap.set("#panel", {{ autoAlpha: {1 if first["layout"] == "split" else 0} }});',
                         f'  gsap.set("#paper", {{ autoAlpha: {1 if first["layout"] in ("card", "stage") else 0} }});',
                         f'  gsap.set("#cardsh", {{ autoAlpha: {1 if first["layout"] == "card" else 0} }});']
                        + ["  " + x for x in cx.init])
    italic, style_fonts = sdef.get("italic_fonts", []), sdef.get("fonts_load", [])
    if style and hasattr(style, "font_setup"):  # the style maps its font roles onto the brand's families
        italic, style_fonts = style.font_setup(brand)
    fontface = theme.resolve_fonts(brand, project, cx.warn, italic=italic)
    f = brand["fonts"]
    fonts_load = [f'900 100px "{f["display"]}"', f'800 54px "{f["display"]}"', f'500 37px "{f["body"]}"',
                  f'600 38px "{f["body"]}"', f'700 22px "{f["body"]}"', f'600 38px "{f["hand"]}"']
    fonts_load += style_fonts
    css = theme.stylesheet(brand, full_style) + layout_css(cx) + ovl_.CSS
    if cx.deck:
        css += deck.CSS + deck_inserts.css(brand)
    if style and hasattr(style, "css"):
        css += style.css(brand, cx)
    if pj.get("_preset"):
        css += feed.css(brand) + kallaway.css(brand)
    gsap_src = ensure_gsap(project)

    def write_html(extra_js=()):
        html = page.build_html(
            title=pj.get("title") or pj.get("slug") or "Reel", css=css, fontface=fontface,
            fonts_load=fonts_load, total=dur_str, beats_html=beats_html if mv else beats_html + "\n" + ovl_html,
            overlays_html=ovl_html if mv else "", captions_html=caps_html,
            tween_js="\n".join("  " + t for t in list(cx.tw) + list(extra_js)), init_js=init_js, gsap_src=gsap_src,
            overlay=overlay, under_html='<div id="paper"></div><div id="cardsh"></div>', motion=mv["page"] if mv else None)
        with open(out, "w") as fh:
            fh.write(html)

    out = os.path.join(project, out_name)
    write_html()

    boxes, err = (None, "skipped")
    if do_measure:
        boxes, err = measure.measure(out)
        if err:
            cx.warn("layout measuring: " + err)
    if cx.deck and mv:   # deck camera: planned on the MEASURED boxes (clamped to the safe panel), then the page again
        djs, dev, drep = deck.plan(cx, beats, boxes, mv["plan"]["transitions"])
        mv["plan"]["events"] = sorted(mv["plan"]["events"] + dev, key=lambda e: e["t"])
        mv["plan"]["deck"] = drep
        motionlayer.M.write_plan(project, mv["plan"])
        write_html(djs)
        print(f"  deck camera: {drep['beats']} panels, {drep['focus']} focus pushes, {drep['punch']} punches, "
              f"{drep['swaps']} swaps")
    qa_place = pip_mask(placement, getattr(cx, "pip_windows", None))   # a head bubble takes the face off the plate
    report = {
        "style": pj.get("style") or "split-deck",
        **({"preset": pj["_preset"]} if pj.get("_preset") else {}),
        "beats": qa_beats(qa_place, (boxes or []) + cx.extra_boxes),
        "canvas": {"w": page.W, "h": page.H}, "seam": SEAM,
        "safe": {"top": 220, "bottom": 1470, "side": 35, "right_clear": {"x": 980, "from_y": 1155}},
        "measured": boxes is not None, "speaker": qa_place, "card": cx.card,
        "inserts": [{"id": b["id"], "t0": round(b["t0"], 3), "t1": round(b["t1"], 3), "layout": b["layout"],
                     "inserts": [i["insert"] for i in b["items"]], "segs": b["segs"]} for b in beats],
        "captions": [{"text": c["text"], "t0": round(c["t0"], 3), "t1": round(c["t1"], 3), "layout": c["layout"],
                      "seg": c["seg"], **({"hidden": True} if c.get("hidden") else {})} for c in chunks],
        "caption_mode": mode, "events": sorted(cx.events, key=lambda e: e["t"]),
        **({"motion": {**mv["plan"]["report"], "transition_spans": [t["span"] for t in mv["plan"]["transitions"]]},
            "motion_events": mv["plan"]["events"]} if mv else {}),
        **({"list": cx.list_plan} if getattr(cx, "list_plan", None) else {}),
        "warnings": cx.warnings, "duration": round(total, 3), "frames": frames, "data_duration": dur_str,
    }
    with open(os.path.join(project, "layout_boxes.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    if getattr(cx, "list_plan", None):  # engine qa.py list_rules reads P/work/list.json
        os.makedirs(os.path.join(project, "work"), exist_ok=True)
        with open(os.path.join(project, "work", "list.json"), "w") as fh:
            json.dump(cx.list_plan, fh, indent=1)
    cfg = os.path.join(project, "hyperframes.json")
    if not os.path.exists(cfg):
        with open(cfg, "w") as fh:
            json.dump({"$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                       "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"}}, fh, indent=2)
    return report


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    rep = compose(args[0], overlay="--safe-overlay" in argv, do_measure="--no-measure" not in argv)
    if "--json" in argv:
        print(json.dumps({"ok": True, "beats": len(rep["beats"]), "captions": len(rep["captions"]),
                          "warnings": rep["warnings"]}))
    else:
        print(f"index.html: {len(rep['inserts'])} inserts, {len(rep['beats'])} qa beats, {len(rep['captions'])} captions, "
              f"{len(rep['warnings'])} warnings, {rep['duration']}s")


if __name__ == "__main__":
    main(sys.argv[1:])
