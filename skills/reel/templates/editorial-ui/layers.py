"""Headline layers: each headline line drawn once as a transparent 1080x1920 PNG in headless Chrome (canvas text, the
bundled serif), plus its ink box. bake.py animates the PNGs (masked rise) and composites them BEHIND the speaker.

Markup in a headline text: "|" starts a new line, "_word_" is italic in the gold accent, everything else is the bold
serif in cream. Each line is fitted on its own to the headline width (cap max_px), then the stack is scaled to fit
between top_min and bottom. The LAST line's ink bottom sits on `bottom` (just under the brow line), so the cap and
forehead cover the lower part of the letters.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import plan as _plan  # noqa: F401  (sets sys.path for stylekit)
import kit  # noqa: E402
import etheme as theme  # noqa: E402

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
{fontface}
html,body{{margin:0;background:transparent}} canvas{{display:block}}
</style></head><body><canvas id="c" width="1080" height="1920"></canvas><script>
const SPEC = {spec};
const ONLY = location.hash.startsWith('#line=') ? Number(location.hash.slice(6)) : -1;
function runs(line){{ const out = []; line.split(/(_[^_]+_)/).forEach(p => {{ if (!p) return;
  if (p.startsWith('_') && p.endsWith('_')) out.push({{t: p.slice(1, -1), it: true}}); else out.push({{t: p, it: false}}); }}); return out; }}
function font(r, px){{ return (r.it ? 'italic ' + SPEC.itw + ' ' : SPEC.w + ' ') + px + 'px "' + SPEC.serif + '"'; }}
function measure(ctx, rs, px){{ let w = 0, asc = 0, desc = 0;
  for (const r of rs) {{ ctx.font = font(r, px); ctx.letterSpacing = (r.it ? SPEC.ls_it : SPEC.ls) * px + 'px';
    const m = ctx.measureText(r.t); w += m.width; asc = Math.max(asc, m.actualBoundingBoxAscent); desc = Math.max(desc, m.actualBoundingBoxDescent); }}
  return {{w, asc, desc}}; }}
(async () => {{
  await Promise.all([document.fonts.load('900 100px "' + SPEC.serif + '"'), document.fonts.load('italic 700 100px "' + SPEC.serif + '"')]);
  await document.fonts.ready;
  const ctx = document.getElementById('c').getContext('2d');
  const lines = SPEC.text.split('|').map(runs);
  let sizes = lines.map(rs => {{ const m = measure(ctx, rs, 100); return Math.min(SPEC.max_px, 100 * SPEC.max_w / m.w); }});
  if (SPEC.same) {{ const s = Math.min(...sizes); sizes = sizes.map(() => s); }}
  let ms = lines.map((rs, i) => measure(ctx, rs, sizes[i]));
  const total = () => ms.reduce((a, m, i) => a + m.asc + m.desc + (i ? SPEC.gap * sizes[i] : 0), 0);
  const room = SPEC.bottom - SPEC.top_min;
  if (total() > room) {{ const k = room / total(); sizes = sizes.map(s => s * k); ms = lines.map((rs, i) => measure(ctx, rs, sizes[i])); }}
  if (Math.min(...sizes) < SPEC.min_px) document.title = 'small';
  let y = SPEC.bottom; const boxes = [];
  for (let i = lines.length - 1; i >= 0; i--) {{
    const m = ms[i], base = y - m.desc, x0 = SPEC.cx - m.w / 2;
    boxes[i] = {{x0: Math.floor(x0 - 4), y0: Math.floor(base - m.asc - 2), x1: Math.ceil(x0 + m.w + 4), y1: Math.ceil(base + m.desc + 2), px: Math.round(sizes[i])}};
    if (ONLY < 0 || ONLY === i) {{
      let x = x0;
      for (const r of lines[i]) {{ ctx.font = font(r, sizes[i]); ctx.letterSpacing = (r.it ? SPEC.ls_it : SPEC.ls) * sizes[i] + 'px';
        ctx.fillStyle = r.it ? SPEC.gold : SPEC.cream; ctx.shadowColor = SPEC.shadow; ctx.shadowBlur = 36; ctx.shadowOffsetY = 10;
        ctx.textBaseline = 'alphabetic'; ctx.fillText(r.t, x, base); x += ctx.measureText(r.t).width; }}
    }}
    y = base - m.asc - SPEC.gap * sizes[i];
  }}
  const pre = document.createElement('pre'); pre.id = 'out'; pre.textContent = JSON.stringify(boxes); document.body.appendChild(pre);
}})();
</script></body></html>"""


def _chrome(args, timeout=90):
    chrome = kit._measure.find_chrome()
    if not chrome:
        raise SystemExit("no headless Chrome (run: npx --yes hyperframes@0.8.34 doctor)")
    return subprocess.run([chrome, "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--hide-scrollbars",
                           "--window-size=1080,1920", "--virtual-time-budget=5000"] + args,
                          capture_output=True, text=True, timeout=timeout)


def render_headline(pl, h, tok, top_min):
    """-> {"lines": [{"png", "x0", "y0", "x1", "y1", "px"}], "small": bool} (cached by content hash)."""
    hc = pl.cfg["headline"]
    s = pl.seg(h["seg"])
    sch = theme.scheme(tok, pl.cfg, h["set"])
    # inside a magazine cover frame the masthead keeps clear of the gold border (border at x 44-1036)
    in_cover = any(c["kind"] == "cover" and c["seg"] == h["seg"] and c["f0"] < h["f1"] and c["f1"] > h["f0"] for c in pl.cards)
    spec = {"text": h["text"], "serif": tok["serif"], "w": hc.get("weight", 800), "itw": hc.get("italic_weight", 600),
            "ls": hc.get("tracking", -0.012), "ls_it": hc.get("tracking_italic", -0.01), "max_px": hc["max_px"],
            "min_px": hc["min_px"], "max_w": min(hc["max_w"], 900) if in_cover else hc["max_w"], "same": bool(h["cfg"].get("same", hc.get("same", False))),
            "gap": hc.get("gap", 0.07), "bottom": h["bottom"], "top_min": top_min,
            "cx": round(h["cfg"].get("cx", 540 if in_cover else min(max(s["anchor"][0], 540 - 40), 540 + 40))),
            "cream": sch["type"], "gold": sch["accent"],
            "shadow": theme.rgba(theme.mix(sch["plate"], "#000000", 0.6), 0.22 if sch["light"] else 0.38)}
    key = hashlib.sha1(json.dumps(spec, sort_keys=True).encode() + open(os.path.join(theme.HERE, "layers.py"), "rb").read()).hexdigest()[:12]
    d = os.path.join(pl.dir, "work", "layers", key)
    meta = os.path.join(d, "meta.json")
    if os.path.exists(meta):
        return kit.jload(meta)
    os.makedirs(d, exist_ok=True)
    ff = theme.fontface(tok, pl.dir).replace("url('assets/", f"url('{Path(pl.dir).as_uri()}/assets/")
    page = os.path.join(d, "page.html")
    with open(page, "w") as f:
        f.write(PAGE.format(fontface=ff, spec=json.dumps(spec)))
    url = Path(page).as_uri()
    r = _chrome(["--dump-dom", url])
    m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
    if not m:
        raise SystemExit(f"headline layer failed for {h['text']!r}: {r.stderr[-300:]}")
    boxes = json.loads(m.group(1))
    lines = []
    for i, b in enumerate(boxes):
        png = os.path.join(d, f"line{i}.png")
        _chrome(["--default-background-color=00000000", f"--screenshot={png}", f"{url}#line={i}"])
        if not os.path.exists(png):
            raise SystemExit(f"headline screenshot failed for {h['text']!r}")
        lines.append({"png": png, **b})
    out = {"lines": lines, "small": "<title>small</title>" in r.stdout, "spec": spec}
    kit.jsave(meta, out)
    return out


def top_reserved(pl, h):
    """Lowest bottom edge of any top-band card on screen during this headline (so the headline starts under it)."""
    band = pl.cfg["band"]["top"]
    low = band
    heights = {"status": 78, "prompt": 96, "countdown": 186, "cover": 54}
    for c in pl.cards:
        if c["seg"] != h["seg"] or c["f1"] <= h["f0"] or c["f0"] >= h["f1"]:
            continue
        low = max(low, band + heights.get(c["kind"], 90))
    return low + (pl.cfg["band"]["gap"] if low > band else 0)


if __name__ == "__main__":
    pl = _plan.Plan(sys.argv[1])
    tok = theme.tokens(pl.proj.brand, pl.cfg)
    for h in pl.headlines:
        r = render_headline(pl, h, tok, top_reserved(pl, h))
        print(h["id"], h["text"], [(l["px"], l["y0"], l["y1"]) for l in r["lines"]], "SMALL" if r["small"] else "")
