"""Kit components, UI family: typer, checklist, progress, odometer, pill, receipt.
Each is a Kit method returning a Piece (html + one RRK call + SFX events). See references/kit.md for the args."""
import math

from rrkit_base import Piece, box, esc, place, sfx, fr  # noqa: F401

SPARK = ('<svg viewBox="0 0 48 48" class="k-spark"><path d="M24 4 C26 17 31 22 44 24 C31 26 26 31 24 44 '
         'C22 31 17 26 4 24 C17 22 22 17 24 4 Z"/></svg>')
CHECK = '<svg viewBox="0 0 48 48"><path pathLength="1" d="M13 25 L21 33 L36 16"/></svg>'


def _wrap(pid, comp, x, y, w, h, kit, theme, inner, z=None, extra=""):
    zs = f"z-index:{z};" if z is not None else ""
    return (f'<div class="rrk rrk-{comp}" id="{pid}" data-layout-allow-overflow style="left:{x}px;top:{y}px;width:{w}px;'
            f'height:{h}px;{zs}{kit.vars(theme)}{extra}">{inner}</div>')


# ---------------------------------------------------------------------------------------------- 1. typer
def typer(self, text, at=0.0, type_at=None, type_until=None, send=None, done=None, done_at=None, until=None,
          labels=("PROMPT", "SENT", "DONE"), pos="top", x=None, y=None, w=960, theme="light", exit="pill", z=None):
    """A pill opens into a prompt bar, types `text` across the spoken words, sends (button press, ring, SENT),
    the result rolls in (DONE, check) and the bar closes back to the pill."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "visual")
    ty0 = cur(type_at, 0.36, "type", rel=t_in)
    ty0 = max(ty0, t_in + 0.3)
    ty1 = cur(type_until, max(0.55, 0.042 * len(text)), "none", rel=ty0)
    ty1 = max(ty1, ty0 + 0.25)
    t_send = cur(send, 0.22, "visual", rel=ty1)
    t_send = max(t_send, ty1 + 0.08)
    t_done = cur(done_at, 0.6, "visual", rel=t_send) if done else None
    if t_done is not None:
        t_done = max(t_done, t_send + 0.35)
    t_out = self.until(until, t_in, (t_done or t_send) + 1.0 - t_in, cur)
    if t_done is not None and t_done > t_out - 0.35:
        t_done = None
    h = 148
    px, py = place(pos, w, h, x, y)
    pid = self.uid("ty")
    chars = "".join(f'<span class="c">{esc(c)}</span>' for c in text)
    lab = (f'<div class="ty-lab"><span class="l0">{esc(labels[0])}</span><span class="l1"><i></i>{esc(labels[1])}</span>'
           f'<span class="l2"><i></i>{esc(labels[2])}</span></div>')
    inner = (f'<div class="ty-shell"><div class="ty-drop"><div class="ty-card" {box("card", t_in, t_out, False)}>'
             f'<div class="ty-ic">{SPARK}</div>{lab}'
             f'<div class="ty-row" style="width:{w - 290}px"><div class="ty-field" {box("text", ty0, t_out)}>'
             f'<span class="ty-text">{chars}</span><span class="ty-caret"></span></div>'
             f'<div class="ty-done" {box("text", t_done or t_out, t_out)}>{esc(done or "")}</div></div>'
             f'<div class="ty-send"><svg class="ty-arrow" viewBox="0 0 80 80"><path d="M40 55 V25 M28 37 L40 25 L52 37"/></svg>'
             f'<svg class="ty-ring" viewBox="0 0 80 80"><circle cx="40" cy="40" r="14"/><path d="M40 26 A14 14 0 0 1 54 40"/></svg>'
             f'<svg class="ty-check" viewBox="0 0 80 80"><path pathLength="1" d="M27 41 L36 50 L54 31"/></svg></div>'
             f'<div class="ty-line"></div></div></div></div>')
    html = _wrap(pid, "typer", px, py, w, h, self, theme, inner, z)
    cfg = {"t_in": t_in, "ty0": ty0, "ty1": ty1, "send": t_send, "done": t_done, "out": t_out, "w": w, "exit": exit}
    ev = [sfx(t_in, "pop", "prompt bar opens"), sfx(t_send, "click", "send")]
    n = len(text)
    for i in range(0, n, 4):
        ev.append(sfx(ty0 + (ty1 - ty0) * i / max(1, n), "type", "typing", "full"))
    if t_done is not None:
        ev.append(sfx(t_done, "pop", "result"))
    ev.append(sfx(t_out, "whoosh", "closes", "full"))
    return self._piece("typer", pid, html, "typer", cfg, ev, t_in, t_out + 0.3,
                       {"text": text, "times": cfg, "box": [px, py, w, h]})


# ---------------------------------------------------------------------------------------------- 2. checklist
def checklist(self, items, ticks=None, at=0.0, until=None, title=None, style="check", pos="top", x=None, y=None,
              w=860, theme="light", exit="blur", z=None):
    """A card lists `items`; each one ticks on its word (ticks: one anchor per item, None = no tick, False = never).
    style 'check' (the row fills in) or 'strike' (done items get crossed out, to-do style)."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "visual")
    tts = []
    ticks = list(ticks or [None] * len(items))
    for i, _ in enumerate(items):
        spec = ticks[i] if i < len(ticks) else None
        if spec is False:
            tts.append(None)
            continue
        t = cur(spec, 0.55 + (0.45 if not tts else 0.0), "visual", rel=(tts[-1] if tts and tts[-1] else t_in + 0.1 * i))
        tts.append(max(t, t_in + 0.3 + 0.07 * i))
    last = max([t for t in tts if t] or [t_in])
    t_out = self.until(until, t_in, last + 1.0 - t_in, cur)
    row_h, top_pad = 104, (118 if title else 44)
    h = top_pad + len(items) * row_h + 30
    px, py = place(pos, w, h, x, y)
    pid = self.uid("ck")
    rows = []
    for i, label in enumerate(items):
        tb = tts[i] or t_in
        rows.append(f'<div class="ck-row" style="top:{top_pad + i * row_h}px"><div class="ck-hl"></div>'
                    f'<div class="ck-ring"><div class="ck-fill"></div>{CHECK}</div>'
                    f'<div class="ck-lbl" {box("text", t_in, t_out)}><span>{esc(label)}</span><i class="ck-strike"></i></div></div>')
    ttl = (f'<div class="ck-ttl" {box("text", t_in, t_out)}><span>{esc(title)}</span></div>' if title else "")
    inner = f'<div class="ck-card" {box("card", t_in, t_out, False)}>{ttl}{"".join(rows)}</div>'
    html = _wrap(pid, "checklist", px, py, w, h, self, theme, inner, z)
    cfg = {"t_in": t_in, "ticks": tts, "out": t_out, "style": style, "exit": exit}
    ev = [sfx(t_in, "pop", "card")] + [sfx(t, "tick", f"tick {items[i]}") for i, t in enumerate(tts) if t]
    ev += [sfx(t_in + 0.12 + 0.07 * i, "whoosh", "row", "full") for i in range(len(items))][:1]
    return self._piece("checklist-tick", pid, html, "checklist", cfg, ev, t_in, t_out + 0.2,
                       {"items": items, "times": cfg, "box": [px, py, w, h]})


# ---------------------------------------------------------------------------------------------- 3. progress
def progress(self, steps, at=0.0, until=None, label="PROGRESS", start=0, notes=None, pos="top", x=None, y=None,
             w=900, theme="light", show_pct=True, unit="%", exit="blur", z=None):
    """A bar fills in steps: steps = [(anchor, value 0-100), ...]; notes = optional text per step under the bar."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "visual")
    ks, prev = [], t_in + 0.2
    for i, (spec, val) in enumerate(steps):
        t = cur(spec, 0.7, "visual", rel=prev)
        t = max(t, prev + 0.18 if ks else t_in + 0.25)
        ks.append([t, float(val)])
        prev = t
    t_out = self.until(until, t_in, ks[-1][0] + 1.1 - t_in, cur)
    h = 236 if notes else 190
    px, py = place(pos, w, h, x, y)
    pid = self.uid("pg")
    note_html = ""
    if notes:
        note_html = '<div class="pg-notes">' + "".join(
            f'<div class="pg-note" {box("text", ks[min(i, len(ks) - 1)][0], t_out)}><span>{esc(n)}</span></div>'
            for i, n in enumerate(notes)) + "</div>"
    marks = "".join(f'<i class="pg-mark" style="left:{v}%"></i>' for _, v in ks if 0 < v < 100)
    inner = (f'<div class="pg-card" {box("card", t_in, t_out, False)}><div class="pg-top">'
             f'<div class="pg-lab" {box("text", t_in, t_out)}>{esc(label)}</div>'
             f'<div class="pg-pct" {box("text", t_in, t_out)}><b class="pg-num">{int(start)}</b>'
             f'<span class="pg-unit">{esc(unit) if show_pct else ""}</span></div></div>'
             f'<div class="pg-track">{marks}<div class="pg-fill"></div><div class="pg-dot"></div></div>{note_html}</div>')
    html = _wrap(pid, "progress", px, py, w, h, self, theme, inner, z)
    cfg = {"t_in": t_in, "keys": ks, "start": start, "out": t_out, "exit": exit, "tw": w - 96}
    ev = [sfx(t_in, "pop", "bar")] + [sfx(t, "tick", f"to {v:g}") for t, v in ks if v < 100]
    ev += [sfx(t + 0.6, "pop", "full bar") for t, v in ks if v >= 100]
    return self._piece("progress-bar", pid, html, "progress", cfg, ev, t_in, t_out + 0.2,
                       {"times": cfg, "box": [px, py, w, h]})


# ---------------------------------------------------------------------------------------------- 4. odometer
def odometer(self, value, at=0.0, land=None, until=None, start=0, decimals=0, prefix="", suffix="", label=None,
             size=230, color="accent", pos="top", x=None, y=None, w=980, theme="light", card=False, exit="blur", z=None):
    """A mechanical counter: digit drums roll from `start` to `value` and lock on `land` (an anchor; default
    0.9 s after `at`); the rightmost drum spins the most; the number stamps when it locks."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "visual")
    t_land = cur(land, 0.95, "stamp", rel=t_in)
    t_land = max(t_land, t_in + 0.45)
    t_out = self.until(until, t_in, t_land + 1.2 - t_in, cur)
    fmt = f"{{:,.{decimals}f}}"
    end_s, start_s = fmt.format(value), fmt.format(start)
    start_s = start_s.rjust(len(end_s), " ")[-len(end_s):] if len(start_s) <= len(end_s) else start_s[-len(end_s):]
    cols, dcount = [], sum(ch.isdigit() for ch in end_s)
    di = 0
    for ch, ch0 in zip(end_s, start_s):
        if not ch.isdigit():
            cols.append(f'<span class="od-sep">{esc(ch)}</span>')
            continue
        d1, d0 = int(ch), int(ch0) if ch0.isdigit() else 0
        turns = di + 1 if dcount > 1 else 1        # left drums turn least, the last one most
        steps = turns * 10 + (d1 - d0) % 10
        seq = "".join(f"<span>{(d0 + k) % 10}</span>" for k in range(steps + 1))
        cols.append(f'<span class="od-col"><span class="od-strip" data-steps="{steps}">{seq}</span></span>')
        di += 1
    h = int(size * 1.08) + (64 if label else 0) + (60 if card else 0)
    px, py = place(pos, w, h, x, y)
    pid = self.uid("od")
    col = self.color(color)
    lab = f'<div class="od-lab" {box("text", t_in, t_out)}>{esc(label)}</div>' if label else ""
    num = (f'<div class="od-num" style="font-size:{size}px;color:{col}" {box("glyph", t_in, t_out)}>'
           f'<span class="od-pre">{esc(prefix)}</span>{"".join(cols)}<span class="od-suf">{esc(suffix)}</span></div>')
    inner = f'<div class="od-shell{" od-card" if card else ""}" {box("card", t_in, t_out, False)}>{lab}{num}</div>'
    html = _wrap(pid, "odometer", px, py, w, h, self, theme, inner, z)
    cfg = {"t_in": t_in, "land": t_land, "out": t_out, "exit": exit}
    ev = [sfx(t_in, "whoosh", "counter in", "full"), sfx(t_land, "stamp", f"locks on {end_s}")]
    k = t_in + 0.12
    while k < t_land - 0.08:
        ev.append(sfx(k, "tick", "drum", "full"))
        k += 0.09
    return self._piece("odometer", pid, html, "odometer", cfg, ev, t_in, t_out + 0.2,
                       {"value": end_s, "times": cfg, "box": [px, py, w, h]})


# ---------------------------------------------------------------------------------------------- 5. label pill
def pill(self, text, at=0.0, strike=None, until=None, exit="tumble", tone="accent", icon=None, logo=None, burst=True,
         size=56, pos="top", x=None, y=None, w=None, theme="light", z=None):
    """A label or logo pill pops in with a burst; on `strike` a line crosses it out and it tumbles away
    (exit 'tumble'); without a strike it leaves with `exit` ('blur', 'fall', 'pop', 'cut') at `until`."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "stamp")
    t_st = cur(strike, 0.9, "visual", rel=t_in) if strike else None
    if t_st is not None:
        t_st = max(t_st, t_in + 0.35)
    t_out = self.until(until, t_in, ((t_st + 0.62) if t_st else t_in + 1.6) - t_in, cur)
    if t_st is not None:
        t_out = min(t_out, t_st + 0.62) if until is None else t_out
    ph = int(size * 1.9)
    est = int(len(text) * size * 0.6 + size * 1.6 + (ph if (icon or logo) else 0))
    pw = w or min(980, est)
    bw, bh = pw + 260, ph + 260
    px, py = place(pos, pw, ph, x, y)
    pid = self.uid("pl")
    lead = ""
    if logo:
        lead = f'<img class="pl-logo" src="{esc(logo)}" alt="">'
    elif icon:
        lead = f'<span class="pl-ic">{icon}</span>'
    r = []
    for i in range(10):
        a = math.radians(i * 36 + 8)
        cx, cy = bw / 2, bh / 2
        rx, ry = pw / 2 + 28, ph / 2 + 26
        x0, y0 = cx + math.cos(a) * rx, cy + math.sin(a) * ry
        x1, y1 = cx + math.cos(a) * (rx + 84), cy + math.sin(a) * (ry + 74)
        r.append(f'<path pathLength="1" d="M{x0:.1f} {y0:.1f} L{x1:.1f} {y1:.1f}"/>')
    burst_svg = (f'<svg class="pl-burst" viewBox="0 0 {bw} {bh}" style="left:{-130}px;top:{-130}px;width:{bw}px;height:{bh}px">'
                 f'{"".join(r)}</svg>' if burst else "")
    inner = (f'<div class="pl-shell">{burst_svg}<div class="pl-body pl-{tone}" style="height:{ph}px;border-radius:{ph // 2}px;'
             f'font-size:{size}px" {box("card", t_in, t_out, False)}>{lead}<span class="pl-t" {box("text", t_in, t_out)}>{esc(text)}</span>'
             f'<i class="pl-strike"></i></div></div>')
    html = _wrap(pid, "pill", px, py, pw, ph, self, theme, inner, z)
    cfg = {"t_in": t_in, "strike": t_st, "out": t_out, "exit": exit if t_st is None or exit != "tumble" else "tumble",
           "burst": bool(burst)}
    ev = [sfx(t_in, "pop", f"pill {text}")]
    if t_st is not None:
        ev += [sfx(t_st, "flip", "strike"), sfx(t_st + 0.2, "whoosh", "tumble", "full")]
    return self._piece("label-pill", pid, html, "pill", cfg, ev, t_in, t_out + 0.1,
                       {"text": text, "times": cfg, "box": [px, py, pw, ph]})


# ---------------------------------------------------------------------------------------------- 6. receipt
def receipt(self, rows, at=0.0, prints=None, total=None, total_at=None, stamp=None, stamp_at=None, until=None,
            title="RECEIPT", sub=None, currency="$", pos="top", x=None, y=None, w=720, theme="light", exit="lift", z=None):
    """A receipt prints out of a slot: rows = [(label, price) or (label, price, was)], each prints on its anchor
    (prints); the total rolls up on total_at; an optional stamp ('PAID', 'SAVED') slams on at stamp_at."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "visual")
    pts, prev = [], t_in + 0.25
    prints = list(prints or [None] * len(rows))
    for i, _ in enumerate(rows):
        t = cur(prints[i] if i < len(prints) else None, 0.38, "visual", rel=prev)
        t = max(t, prev + 0.12 if pts else t_in + 0.3)
        pts.append(t)
        prev = t
    if total is None:
        total = sum(float(r[1]) for r in rows)
    t_tot = cur(total_at, 0.4, "visual", rel=prev)
    t_tot = max(t_tot, prev + 0.2)
    t_stp = cur(stamp_at, 0.55, "stamp", rel=t_tot) if stamp else None
    if t_stp is not None:
        t_stp = max(t_stp, t_tot + 0.3)
    t_out = self.until(until, t_in, (t_stp or t_tot) + 1.1 - t_in, cur)
    row_h, head_h = 74, (150 if sub else 112)
    paper_h = head_h + len(rows) * row_h + 150
    h = paper_h + 40
    px, py = place(pos, w, h, x, y)
    pid = self.uid("rc")

    def money(v):
        return f"{currency}{float(v):,.2f}" if float(v) % 1 else f"{currency}{float(v):,.0f}"
    rws = []
    for i, r in enumerate(rows):
        was = f'<s class="rc-was">{esc(money(r[2]))}</s>' if len(r) > 2 and r[2] is not None else ""
        rws.append(f'<div class="rc-row" style="top:{head_h + i * row_h}px" {box("text", pts[i], t_out)}>'
                   f'<span class="rc-l">{esc(r[0])}</span><i class="rc-dots"></i>{was}<span class="rc-p">{esc(money(r[1]))}</span></div>')
    dec = 2 if float(total) % 1 else 0
    sub_html = f'<div class="rc-sub">{esc(sub)}</div>' if sub else ""
    stamp_top = head_h + len(rows) * row_h + 8
    stamp_html = (f'<div class="rc-stamp" style="top:{stamp_top}px" {box("text", t_stp or t_out, t_out)}><span>{esc(stamp)}</span></div>'
                  if stamp else "")
    inner = (f'<div class="rc-slot"></div><div class="rc-feed"><div class="rc-win" style="height:{paper_h}px">'
             f'<div class="rc-paper" style="height:{paper_h}px" {box("card", t_in, t_out, False)}>'
             f'<div class="rc-head" {box("text", t_in, t_out)}><b>{esc(title)}</b>{sub_html}</div>{"".join(rws)}'
             f'<div class="rc-tot" style="top:{head_h + len(rows) * row_h + 20}px" {box("text", t_tot, t_out)}>'
             f'<span>TOTAL</span><b><em>{esc(currency)}</em><span class="rc-tn">0</span></b></div>{stamp_html}</div></div>'
             f'<div class="rc-teeth"></div></div>')
    html = _wrap(pid, "receipt", px, py, w, h, self, theme, inner, z)
    cfg = {"t_in": t_in, "prints": pts, "total": float(total), "dec": dec, "tot": t_tot, "stamp": t_stp, "out": t_out,
           "row_h": row_h, "head_h": head_h, "paper_h": paper_h, "exit": exit}
    ev = [sfx(t_in, "click", "slot"), sfx(t_tot, "pop", "total")]
    ev += [sfx(t, "tick", f"row {rows[i][0]}", "full") for i, t in enumerate(pts)]
    if t_stp is not None:
        ev.append(sfx(t_stp, "stamp", f"stamp {stamp}"))
    return self._piece("receipt", pid, html, "receipt", cfg, ev, t_in, t_out + 0.2,
                       {"times": cfg, "box": [px, py, w, h]})


UI = {"typer": typer, "checklist": checklist, "progress": progress, "odometer": odometer, "pill": pill, "receipt": receipt}
