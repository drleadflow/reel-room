"""LIST STACK hero moment: when an item is called out it gets the whole band above the head first, then collapses
into its slot in the list.

  1. call-out (item `on`): the list steps back (blur), a giant numeral slams in (2.6x, blur, tilt) with a camera punch
     on the cut, the item name stamps in letter by letter on its word
  2. payoff (hero.payoff, optional): the numeral and the name tuck into a compact header, one or more component-kit
     pieces (templates/kit: checklist, odometer, pill, progress ...) show the item's payoff on its words
  3. collapse (hero.until): the payoff leaves, the numeral flies into its badge in the list (scales down onto it), the
     list steps forward again and the row lands lit (style.py _row_on)

Geometry is fixed in frame px so the flight is exact: the numeral box is centred at (540, y0 + 160).
"""
import json
import os
import sys

from ctx import esc, snap

KIT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kit")
NUM_W, NUM_H, NUM_PX = 440, 320, 400        # giant numeral box (frame px) and font size
LBL_PX = 92                                  # item name in the call-out
COMPACT = {"k": 0.36, "cx": 160, "cy": 64}   # numeral in the compact header: scale, centre (x, y from y0)
PAYOFF_TOP = 156                             # payoff pieces start this far below y0
FLY = 0.44                                   # collapse flight


def _js(cx, line):
    cx.tw.append(line)


def _ft(cx, sel, t, frm, to, dur, ease):
    v = dict(to, duration=dur, ease=ease, immediateRender=False)
    _js(cx, f"tl.fromTo({json.dumps(sel)},{json.dumps(frm)},{json.dumps(v)},{snap(t)});")


def _kit(cx, base):
    if KIT not in sys.path:
        sys.path.insert(0, KIT)
    import rrkit
    k = rrkit.Kit(cx.brand, cx.words.w, base=base, prefix="k")
    k._uid = cx.uid
    return rrkit, k


def _payoff(cx, rrkit, k, spec, x_in, y, t_end, y1):
    """One kit piece from a project spec {"comp": "checklist", ...args}; placed in the band under the header."""
    args = {kk: v for kk, v in spec.items() if kk != "comp"}
    w = int(args.get("w", 880 if spec["comp"] != "odometer" else 900))
    args.setdefault("w", w)
    args.setdefault("x", round((1080 - w) / 2) if x_in is None else x_in)
    args.setdefault("y", y)
    if "until" not in args:
        args["until"] = round(t_end - k.base, 3)
    if spec["comp"] in ("odometer",):
        args.setdefault("size", 190)
    comp = spec["comp"]
    piece = rrkit.build(k, comp, **args) if comp in rrkit.COMPONENTS else getattr(k, comp)(**args)
    px, py, pw, ph = piece.meta.get("box", [0, y, w, 0])
    if py + ph > y1 + 4:
        cx.warn(f"list-stack hero: {spec['comp']} ends at y {py + ph}, below the band ({y1}); trim it")
    return rrkit.mount(cx, piece), piece


def _payoff_section(cx, tp, t_x, window=1.5):
    """A new payoff piece is a new beat of the item: the first cut within `window` s after it (and before the collapse)
    counts as a section change, so the engine may move the footage there while the graphics hold still."""
    nxt = sorted((sg["t0"], sg["id"]) for sg in getattr(cx, "segs", []) if tp < sg["t0"] <= min(tp + window, t_x + 0.1))
    if nxt:
        cx.section_cuts = set(getattr(cx, "section_cuts", None) or ()) | {nxt[0][1]}


def build(cx, b, lid, i, it, geo):
    """-> (html, t_row): the hero layer for item i and the time its row lands in the list.
    geo: {"y0", "y1", "badge_c": (x, y) frame px, "badge_px": glyph px}"""
    h = it["hero"] if isinstance(it.get("hero"), dict) else {}
    hid = f"{lid}h{i}"
    y0, y1 = geo["y0"], geo["y1"]
    ton = cx.when(it["on"], b, 0.0)
    t_lbl = max(ton + 0.25, cx.cue(it["at"], b, after=ton, lead="type", fallback=0.6)) if it.get("at") else ton + 0.4
    pays = h.get("payoff") or []
    t_x = (cx.cue(h["until"], b, after=ton, lead="none", fallback=3.0) if str(h.get("until", "")).startswith("@")
           else cx.when(h.get("until"), b, 3.0) if h.get("until") is not None else ton + 2.2)
    t_x = max(t_x, ton + 0.8)
    ncx, ncy = 540, y0 + NUM_H / 2
    # 1. call-out: the list steps back, the numeral slams, the name stamps letter by letter
    cx.to(f"#{lid}L", ton, {"opacity": 0, "filter": "blur(10px)", "scale": 0.97}, dur=0.18, ease="power3.in")
    cx.set(f"#{hid}", ton, {"autoAlpha": 1})
    _ft(cx, f"#{hid}n", ton, {"opacity": 0, "scale": 2.6, "rotation": -8, "filter": "blur(26px)"},
        {"opacity": 1, "scale": 1, "rotation": 0, "filter": "blur(0px)"}, 0.26, "power4.out")
    _js(cx, f"RRM.squash(tl,'#{hid}n',{snap(ton + 0.26)},{{k:0.9,origin:'50% 50%'}});")
    cx.event(ton, "pop", f"item {i + 1} numeral slams")
    lab = esc(it.get("label", ""))
    show_lbl = bool(lab) and t_lbl < t_x - 0.4      # a name spoken after the collapse lands in the list row instead
    if show_lbl:
        _js(cx, f"RRM.enter('letterStamp',tl,document.querySelector('#{hid}l'),{snap(t_lbl)},{{stagger:0.045,dur:0.22,from:1.5}});")
        cx.event(t_lbl, "click", f"item {i + 1} name")
    html = [f'<div class="lshn" id="{hid}n" style="left:{ncx - NUM_W / 2:.0f}px;top:{y0}px;width:{NUM_W}px;height:{NUM_H}px;'
            f'font-size:{NUM_PX}px;line-height:{NUM_H}px" {cx.box("glyph", ton, t_x, True)}>{i + 1}</div>',
            f'<div class="lshl" id="{hid}l" style="top:{y0 + NUM_H + 8}px;font-size:{LBL_PX}px" data-fit="960,40" '
            f'{cx.box("text", t_lbl, t_x, True)}>{lab}</div>']
    if pays:
        rrkit, k = _kit(cx, ton)
        cur = k.cursor()
        t_c = max(t_lbl + 0.6, cur(pays[0].get("at"), 0.8, "visual") - 0.36)
        dx, dy = COMPACT["cx"] - ncx, y0 + COMPACT["cy"] - ncy
        cx.to(f"#{hid}n", t_c, {"x": dx, "y": dy, "scale": COMPACT["k"]}, dur=0.5, ease="expo.inOut")
        cx.to(f"#{hid}l", t_c, {"opacity": 0, "y": -30, "filter": "blur(8px)"}, dur=0.16, ease="power3.in")
        _js(cx, f"RRM.enter('maskPush',tl,document.querySelector('#{hid}c'),{snap(t_c + 0.2)},{{dur:0.36}});")
        cx.event(t_c, "whoosh", f"item {i + 1} header tucks in")
        html.append(f'<div class="lshc" id="{hid}c" style="top:{y0 + 22}px;left:{COMPACT["cx"] + 90}px" '
                    f'data-fit="740,30" {cx.box("text", t_c, t_x, True)}>{lab}</div>')
        for j, p in enumerate(pays):
            keep = p.pop("keep", False) if isinstance(p, dict) else False    # stays up under the next piece
            end = t_x if j + 1 == len(pays) or keep else max(ton + 0.5, cur(pays[j + 1].get("at"), 1.0, "visual") - 0.05)
            ph, piece = _payoff(cx, rrkit, k, p, p.get("x"), y0 + PAYOFF_TOP, end, y1)
            html.append(ph)
            if j and h.get("transitions", True):
                _payoff_section(cx, piece.t0, t_x)
        cx.to(f"#{hid}c", t_x - 0.04, {"opacity": 0, "filter": "blur(8px)"}, dur=0.16, ease="power3.in")
    elif show_lbl:
        cx.to(f"#{hid}l", t_x - 0.04, {"opacity": 0, "filter": "blur(8px)"}, dur=0.16, ease="power3.in")
    # 3. collapse: the numeral flies onto its badge, the list steps forward again
    bx, by = geo["badge_c"]
    k_to = geo["badge_px"] / NUM_PX
    cx.to(f"#{hid}n", t_x, {"x": bx - ncx, "y": by - ncy, "scale": k_to}, dur=FLY, ease="expo.inOut")
    cx.set(f"#{hid}", t_x + FLY, {"autoAlpha": 0})
    cx.to(f"#{lid}L", t_x + 0.26, {"opacity": 1, "filter": "blur(0px)", "scale": 1}, dur=0.3, ease="expo.out")
    cx.event(t_x, "whoosh", f"item {i + 1} collapses into the list")
    cx.init.append(f'gsap.set("#{hid}",{{autoAlpha:0}});')
    return f'<div class="lsh" id="{hid}">{"".join(html)}</div>', t_x + FLY - 0.06


def css():
    return """
.lsh{position:absolute;left:0;top:0;width:1080px;height:1920px;pointer-events:none}
.lshn{position:absolute;text-align:center;font-family:var(--fd);font-weight:900;letter-spacing:-.06em;color:var(--accent);
  transform-origin:50% 50%;text-shadow:0 2px 0 rgba(255,255,255,.35),0 18px 50px rgba(122,30,46,.35)}
.lshl{position:absolute;left:0;width:1080px;text-align:center;font-family:var(--fd);font-weight:900;line-height:1;
  letter-spacing:-.03em;word-spacing:.05em;text-transform:uppercase;color:var(--ink);white-space:nowrap;opacity:0;
  text-shadow:0 2px 0 rgba(255,255,255,.5),0 10px 30px rgba(255,255,255,.55)}
.lshc{position:absolute;font:900 64px/1.1 var(--fd);letter-spacing:-.03em;word-spacing:.06em;text-transform:uppercase;color:var(--ink);
  white-space:nowrap;opacity:0;text-shadow:0 2px 0 rgba(255,255,255,.5)}
.lsL{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:540px 420px}
"""
