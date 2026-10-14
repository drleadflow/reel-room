"""Card-style top-panel inserts. Each: fn(cx, beat, args) -> html. Coordinates are frame pixels (panel = 1080x960).
Entrances only, 0.25-0.4 s. Times: numbers are seconds after the beat starts, '@word' anchors to the spoken word."""
from ctx import esc

CHECK = ('<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="#fff" stroke-width="3.2" '
         'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def place(a, height, default=250):
    """Top y for a block `height` px tall: explicit `y`, else centred in the visible panel (220-940) when it is
    the only thing in the panel (`_alone`), else `default`."""
    if "y" in a:
        return a["y"]
    if a.get("_alone"):
        y0, y1 = a.get("_area", (220, 940))
        return round(y0 + (y1 - y0 - height) / 2)
    return default


def area_style(a):
    """Flex row style that centres a block in the beat's visible band (split panel: 220-940)."""
    y0, y1 = a.get("_area", (220, 940))
    return f"top:{y0}px;height:{y1 - y0}px"


def _rise(cx, beat, sel, t=None, dy=22, dur=0.34, frm=0.55):
    """Card entrance that starts ON the cut frame from a visible state (opacity .55), so the cut reads as a new shot."""
    a0 = beat.get("anchor_t0", beat["t0"])
    cx.enter(beat, sel, a0 if t is None else t, {"opacity": frm, "y": dy}, dur=dur)


def hook_card(cx, beat, a):
    l1 = a.get("l1") or cx.hook.get("l1", "")
    l2 = a.get("l2") or cx.hook.get("l2", "")
    gid, t0, t1 = cx.uid("hk"), beat["t0"], beat["t1"]
    centred = a.get("_alone") and "y" not in a
    row = (f'style="{area_style(a)};align-items:center"' if centred else f'style="top:{a.get("y", 250)}px"')
    tx = lambda: cx.box("text", t0, t1, True)  # noqa: E731
    if a.get("enter"):
        _rise(cx, beat, f"#{gid}", cx.when(None if a["enter"] is True else a["enter"], beat))
    return (f'<div class="centerrow" {row}><div class="card-acc" id="{gid}" {cx.box("card", t0, t1)}>'
            f'<span class="l l1" data-fitgroup="{gid}" data-fitmax="{a.get("max", 930)}" {tx()}>{esc(l1)}</span>'
            f'<span class="l l2" data-fitgroup="{gid}" data-fitmax="{a.get("max", 930)}" {tx()}>{esc(l2)}</span>'
            f'</div></div>')


def polaroids(cx, beat, a):
    items = a["items"]
    n, y = len(items), a.get("y", 580)
    rots = a.get("rot", [-4, -1.5, 3.5, -2.5])
    dys = a.get("dy", [10, -8, 12, 0])
    w, side = 340, 54
    if n == 1:
        xs = [(1080 - w) // 2]
    else:
        step = min((1080 - 2 * side - w) / (n - 1), w + 18)
        x0 = (1080 - (w + step * (n - 1))) / 2
        xs = [x0 + step * i for i in range(n)]
    out = []
    for i, it in enumerate(items):
        cx.check_asset(it["img"])
        pid = cx.uid("pol")
        t = cx.when((a.get("at") or [None] * n)[i] if a.get("at") else None, beat, 0.4 + 0.45 * i)
        cx.enter(beat, f"#{pid}", t, {"opacity": 0, "y": 50, "scale": 0.9},
                 {"opacity": 1, "y": 0, "scale": 1}, dur=0.32, ease="back.out(1.5)")
        t0 = max(t, beat["t0"])
        out.append(
            f'<div class="pol" id="{pid}" style="left:{xs[i]:.0f}px;top:{y + dys[i % len(dys)]}px;rotate:{rots[i % len(rots)]}deg" '
            f'{cx.box("polaroid", t0, beat["t1"])}><div class="ph" style="background-image:url(\'{esc(it["img"])}\')"></div>'
            f'<div class="cp" {cx.box("text", t0, beat["t1"], True)}><span>{esc(it["name"])}</span><b>{esc(it["result"])}</b></div></div>')
    return "".join(out)


def number(cx, beat, a):
    uid, t0, t1 = cx.uid("num"), beat["t0"], beat["t1"]
    tx = lambda: cx.box("text", t0, t1, True)  # noqa: E731
    a0 = beat.get("anchor_t0", t0)
    # number lands on the cut (from a visible state), title and sub on their words when given (title_at / sub_at)
    times = {"n": cx.when(a.get("n_at"), beat, 0.0), "t": cx.when(a.get("title_at"), beat, 0.06),
             "s": cx.when(a.get("sub_at"), beat, 0.3)}
    for suffix, start in (("n", 0.55), ("t", 0.55), ("s", 0.0)):
        if suffix == "s" and not a.get("sub"):
            continue
        on_word = a.get({"n": "n_at", "t": "title_at", "s": "sub_at"}[suffix]) is not None
        frm = {"opacity": 0, "y": 26} if on_word else {"opacity": start, "y": 22}
        cx.enter(beat, f"#{uid}{suffix}", times[suffix], frm, dur=0.34)
        if on_word:
            cx.event(times[suffix], "whoosh" if suffix == "t" else "pop", f"number {a.get('n')} {suffix}")
    if "y" in a:
        wrap = f"top:{a['y']}px"
    elif a.get("_alone"):
        wrap = f"{area_style(a)};justify-content:center"
    else:
        wrap = f"top:{300 + a.get('dy', 0)}px"
    sub = f'<div class="s" id="{uid}s" {tx()}>{esc(a["sub"])}</div>' if a.get("sub") else ""
    kick = f'<div class="k" {tx()}>{esc(a["kicker"])}</div>' if a.get("kicker") else ""
    return (f'<div class="num numwrap" style="{wrap}">{kick}<div class="n" id="{uid}n" {tx()}>{esc(a["n"])}</div>'
            f'<div class="t" id="{uid}t" data-fit="960,52" {tx()}>{esc(a["title"])}</div>{sub}</div>')


def table(cx, beat, a):
    cols, rows = a.get("cols", ["TEST", "WHAT IT SHOWS"]), a["rows"]
    tid, t0, t1 = cx.uid("tbl"), beat["t0"], beat["t1"]
    rh = 100
    height = 112 + len(rows) * rh + 14
    top = place(a, height)
    inst = a.get("instant", 0)
    reveal = a.get("reveal") or [None] * len(rows)
    hl = a.get("highlight")
    parts = []
    for i, (c1, c2) in enumerate(rows):
        rid = f"{tid}r{i}"
        spec = reveal[i] if i < len(reveal) else None
        t = cx.when(spec, beat, 0.2 + 0.25 * i)
        if i >= inst and spec is False:  # row exists (card height) but stays blank in this beat
            cx.set(f"#{rid}", beat["t0"], {"opacity": 0})
            t = t1 + 1
        elif i >= inst:
            cx.enter(beat, f"#{rid}", t, {"opacity": 0, "y": 14}, dur=0.28)
        tb = max(t, t0) if i >= inst else t0
        rowhl = ""
        if hl and hl["row"] == i:
            ht = cx.when(hl.get("at"), beat, 0.6)
            cx.to(f"#{rid}h", max(ht, t0), {"opacity": 1}, dur=0.3)
            rowhl = f'<div class="rowhl" id="{rid}h"></div>'
        parts.append(f'<div class="row" id="{rid}" style="top:{100 + i * rh}px;height:{rh}px">{rowhl}'
                     f'<span class="a" {cx.box("text", tb, t1, True)}>{esc(c1)}</span>'
                     f'<span class="b" {cx.box("text", tb, t1, True)}>{esc(c2)}</span></div>')
    tag = a.get("tag")
    tag_html = ""
    if tag:
        gid = f"{tid}g"
        tt = cx.when(tag.get("at"), beat, 1.0)
        cx.enter(beat, f"#{gid}", tt, {"opacity": 0, "scale": 0.7}, {"opacity": 1, "scale": 1}, dur=0.3, ease="back.out(2)")
        ry = 100 + tag.get("row", hl["row"] if hl else 0) * rh
        tag_html = (f'<div class="tag" id="{gid}" style="right:34px;top:{ry - 24}px" '
                    f'{cx.box("text", max(tt, t0), t1, True)}>{esc(tag["text"])}</div>')
    _rise(cx, beat, f"#{tid}") if a.get("enter", True) else None
    head = "".join(f"<span>{esc(c)}</span>" for c in cols)
    return (f'<div class="card tbl" id="{tid}" style="left:90px;top:{top}px;width:900px;height:{height}px" '
            f'{cx.box("card", t0, t1)}><div class="hd" {cx.box("text", t0, t1, True)}>{head}</div>'
            f'<div class="hdline"></div>{"".join(parts)}{tag_html}</div>')


def calendar(cx, beat, a):
    cid, t0, t1 = cx.uid("cal"), beat["t0"], beat["t1"]
    n, cols = a.get("n", 16), a.get("cols", 8)
    shift = place({k: v for k, v in a.items() if k != "y"}, 414) - 250 if "y" not in a else 0
    cell, x0, y0, pitch_y = 84, a.get("x0", 150), a.get("y", 360 + shift), 99
    gap = (780 - cols * cell) / (cols - 1)
    sel = {s["n"]: s for s in a.get("select", [])}
    cells = []
    for i in range(n):
        num = i + 1
        r, c = divmod(i, cols)
        on = ""
        if num in sel:
            s = sel[num]
            oid = f"{cid}o{num}"
            t = cx.when(s.get("at"), beat, 0.5)
            cx.enter(beat, f"#{oid}", t, {"opacity": 0}, {"opacity": 1}, dur=0.26)
            on = f'<div class="on{" soft" if s.get("soft") else ""}" id="{oid}">{num}</div>'
        cells.append(f'<div class="cell" style="left:{x0 + c * (cell + gap):.1f}px;top:{y0 + r * pitch_y}px" '
                     f'{cx.box("text", t0, t1, True)}>{num}{on}</div>')
    pills = []
    for p in a.get("pills", []):
        pid = cx.uid("pl")
        t = cx.when(p.get("at"), beat, 1.0)
        cx.enter(beat, f"#{pid}", t, {"opacity": 0, "y": 16}, dur=0.3)
        strike = ""
        if p.get("strike_at") is not None:
            st = cx.when(p["strike_at"], beat, 1.5)
            cx.enter(beat, f"#{pid}s", st, {"opacity": 1, "scaleX": 1e-3}, {"opacity": 1, "scaleX": 1}, dur=0.3, ease="power2.out")
            strike = f'<span class="strike" id="{pid}s" style="transform-origin:0 50%"></span>'
        pills.append(f'<div class="pillx {p.get("kind", "good")}" id="{pid}" {cx.box("text", max(t, t0), t1, True)}>'
                     f'{esc(p["text"])}{strike}</div>')
    title = (f'<div class="ttl abs" style="left:0;top:{a.get("ty", 250 + shift)}px" data-fit="1000,40" '
             f'{cx.box("text", t0, t1, True)}>{esc(a.get("title", ""))}</div>')
    _rise(cx, beat, f"#{cid}") if a.get("enter", True) else None
    return (f'<div class="cal" id="{cid}">{title}{"".join(cells)}'
            f'<div class="centerrow" style="top:{y0 + 2 * pitch_y + 38}px;gap:34px">{"".join(pills)}</div></div>')


def checklist(cx, beat, a):
    cid, t0, t1 = cx.uid("chk"), beat["t0"], beat["t1"]
    items = a["items"]
    ticks = a.get("ticks") or [None] * len(items)
    inst = set(a.get("instant", []))
    ink = cx.brand["colors"]["ink"]
    h = 100 + len(items) * 92 + 24
    rows = []
    for i, label in enumerate(items):
        rid = f"{cid}r{i}"
        done = i in inst
        if not done and not (i < len(ticks) and ticks[i] is False):
            t = cx.when(ticks[i] if i < len(ticks) else None, beat, 0.4 + 0.4 * i)
            cx.enter(beat, f"#{rid}f", t, {"opacity": 0, "scale": 0.4}, {"opacity": 1, "scale": 1}, dur=0.28, ease="back.out(2)")
            cx.to(f"#{rid}l", max(t, t0), {"color": ink}, dur=0.2)
        rows.append(f'<div class="row{" done" if done else ""}" style="top:{100 + i * 92}px"><div class="ring">'
                    f'<div class="fill" id="{rid}f">{CHECK}</div></div>'
                    f'<div class="lbl" id="{rid}l" {cx.box("text", t0, t1, True)}>{esc(label)}</div></div>')
    _rise(cx, beat, f"#{cid}") if a.get("enter", True) else None
    return (f'<div class="card chk" id="{cid}" style="left:120px;top:{place(a, h)}px;width:840px;height:{h}px" '
            f'{cx.box("card", t0, t1)}><div class="ttl" {cx.box("text", t0, t1, True)}>{esc(a.get("title", ""))}</div>'
            f'{"".join(rows)}</div>')


def two_path(cx, beat, a):
    cid, t0, t1 = cx.uid("two"), beat["t0"], beat["t1"]
    rows = a["rows"]
    h = 40 + len(rows) * 150 + 20
    parts = []
    for i, r in enumerate(rows):
        rid = f"{cid}r{i}"
        if i > 0 or r.get("at") is not None:
            t = cx.when(r.get("at"), beat, 0.5)
            cx.enter(beat, f"#{rid}", t, {"opacity": 0, "y": 18}, dur=0.3)
        else:
            t = t0
        top = 30 + i * 150
        if i:
            parts.append(f'<div class="sep" style="top:{top}px"></div>')
        parts.append(f'<div class="rw" id="{rid}" style="top:{top}px"><div class="cond {r.get("tone", "a" if i == 0 else "b")}" '
                     f'{cx.box("text", max(t, t0), t1, True)}>{esc(r["cond"])}</div><div class="arr">&rarr;</div>'
                     f'<div class="res" data-fit="470,34" {cx.box("text", max(t, t0), t1, True)}>{esc(r["result"])}</div></div>')
    _rise(cx, beat, f"#{cid}") if a.get("enter", True) else None
    return (f'<div class="card two" id="{cid}" style="left:60px;top:{place(a, h, 300)}px;width:960px;height:{h}px" '
            f'{cx.box("card", t0, t1)}>{"".join(parts)}</div>')


def strike_pill(cx, beat, a):
    sid, t0, t1 = cx.uid("sp"), beat["t0"], beat["t1"]
    y = place(a, 132 + (110 if a.get("sub") else 0), 330)
    st = cx.when(a.get("strike_at"), beat, 0.9)
    _rise(cx, beat, f"#{sid}", cx.when(a.get("at"), beat, 0.0))
    cx.enter(beat, f"#{sid}l", st, {"opacity": 1, "scaleX": 1e-3}, {"opacity": 1, "scaleX": 1}, dur=0.3)
    cx.to(f"#{sid}t", max(st, t0), {"opacity": 0.45}, dur=0.25)
    sub = ""
    if a.get("sub"):
        cx.enter(beat, f"#{sid}b", st + 0.3, {"opacity": 0, "y": 14}, dur=0.3)
        sub = (f'<div class="centerrow" style="top:{y + 190}px"><div class="sub" id="{sid}b" style="color:var(--alert)" '
               f'{cx.box("text", max(st + .3, t0), t1, True)}>{esc(a["sub"])}</div></div>')
    return (f'<div class="centerrow" id="{sid}" style="top:{y}px"><div class="strikepill" {cx.box("card", t0, t1)}>'
            f'<span id="{sid}t" data-fit="920,40" {cx.box("text", t0, t1, True)}>{esc(a["text"])}</span>'
            f'<span class="ln" id="{sid}l" style="transform-origin:0 50%"></span></div></div>{sub}')


def cta(cx, beat, a):
    cid, t0, t1 = cx.uid("cta"), beat["t0"], beat["t1"]
    gid = cx.uid("g")
    centred = a.get("_alone") and "y" not in a
    row = f'style="{area_style(a)};align-items:center"' if centred else f'style="top:{a.get("y", 330)}px"'
    l1, l2 = a["l1"], a["l2"]
    emoji = f' <span style="font-size:.86em">{a["emoji"]}</span>' if a.get("emoji") else ""
    small = (f'<div class="sub" style="font-weight:800;color:var(--ink);font-family:var(--fd);font-size:40px" data-fit="980,28" '
             f'{cx.box("text", t0, t1, True)}>{esc(a["small"])}</div>' if a.get("small") else "")
    _rise(cx, beat, f"#{cid}", dy=26)
    return (f'<div class="centerrow" {row}><div id="{cid}" style="display:flex;flex-direction:column;align-items:center;gap:62px">'
            f'<div class="card-acc" {cx.box("card", t0, t1)}>'
            f'<span class="l l1" data-fitgroup="{gid}" data-fitmax="{a.get("max", 800)}" {cx.box("text", t0, t1, True)}>{esc(l1)}</span>'
            f'<span class="l l2" data-fitgroup="{gid}" data-fitmax="{a.get("max", 800)}" {cx.box("text", t0, t1, True)}>{esc(l2)}{emoji}</span>'
            f'</div>{small}</div></div>')


def stat(cx, beat, a):
    """Big number stat: small caps label, optional lead word ("over"), a huge value in accent, unit, and a tag pill.
    args: label, pre, value, unit, tag {text, at}, at (when the value lands), y."""
    sid, t0, t1 = cx.uid("st"), beat["t0"], beat["t1"]
    tx = lambda t: cx.box("text", max(t, t0), t1, True)  # noqa: E731
    h = 86 + 300 + (110 if a.get("tag") else 0)
    top = place(a, h)
    a0 = beat.get("anchor_t0", t0)
    vt = cx.when(a.get("at"), beat, 0.0)
    _rise(cx, beat, f"#{sid}l", a0, dy=16)
    if a.get("pre"):
        pt = cx.when(a.get("pre_at"), beat, 0.0)
        cx.enter(beat, f"#{sid}p", pt, {"opacity": 0, "x": -24}, dur=0.3)
    cx.enter(beat, f"#{sid}v", vt, {"opacity": 0, "scale": 1.35}, {"opacity": 1, "scale": 1}, dur=0.34, ease="back.out(1.6)")
    cx.event(vt, "thud", f"stat {a.get('value')}")
    pre = (f'<span class="pre" id="{sid}p" {tx(cx.when(a.get("pre_at"), beat, 0.0))}>{esc(a["pre"])}</span>'
           if a.get("pre") else "")
    unit = f'<span class="unit" {tx(vt)}>{esc(a["unit"])}</span>' if a.get("unit") else ""
    tag = ""
    if a.get("tag"):
        tg = a["tag"]
        tt = cx.when(tg.get("at"), beat, 1.0)
        cx.enter(beat, f"#{sid}g", tt, {"opacity": 0, "y": 16, "scale": 0.9}, {"opacity": 1, "y": 0, "scale": 1}, dur=0.3,
                 ease="back.out(1.8)")
        cx.event(tt, "pop", "stat tag")
        tag = (f'<div class="centerrow" style="top:{top + 396}px"><div class="tag stat-tag" id="{sid}g" style="position:relative" '
               f'{tx(tt)}>{esc(tg["text"])}</div></div>')
    # a faint copy of the value sits there from the cut, so the panel never reads empty before the number lands
    ghost = f'<span class="v ghost">{esc(a["value"])}</span>' if a.get("ghost", True) else ""
    return (f'<div class="statwrap" style="top:{top}px">'
            f'<div class="lbl" id="{sid}l" {cx.box("text", t0, t1, True)}>{esc(a.get("label", ""))}</div>'
            f'<div class="row">{pre}<span class="vbox">{ghost}<span class="v" id="{sid}v" {tx(vt)}>{esc(a["value"])}</span></span>{unit}</div></div>{tag}')
