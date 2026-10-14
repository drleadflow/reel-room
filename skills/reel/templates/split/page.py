"""index.html assembly: root markup, the in-page runtime (font wait, text fitting, box measuring) and the GSAP timeline."""
import json

from ctx import esc

W, H = 1080, 1920

RUNTIME = r"""
const RR_MEASURE = location.hash === '#measure';
function rrRange(el){ const r = document.createRange(); r.selectNodeContents(el); return r; }
function rrFitEl(el){
  const [max, min] = el.dataset.fit.split(',').map(Number), pad = Number(el.dataset.fitpad || 0);
  if (!el.dataset.base) el.dataset.base = parseFloat(getComputedStyle(el).fontSize);
  let fs = Number(el.dataset.base);
  el.style.fontSize = fs + 'px';
  for (let i = 0; i < 4; i++) {
    const w = rrRange(el).getBoundingClientRect().width + pad;
    if (w <= max + 0.5 || fs <= (min || 20)) break;
    fs = Math.max(min || 20, fs * (max / w) * 0.995);
    el.style.fontSize = fs + 'px';
  }
}
function rrFitAll(){
  document.querySelectorAll('[data-fit]').forEach(rrFitEl);
  const groups = {};
  document.querySelectorAll('[data-fitgroup]').forEach(el => { (groups[el.dataset.fitgroup] = groups[el.dataset.fitgroup] || []).push(el); });
  Object.values(groups).forEach(list => {
    let k = 1;
    list.forEach(el => { el.style.fontSize = ''; k = Math.min(k, Number(el.dataset.fitmax) / rrRange(el).getBoundingClientRect().width); });
    if (k < 1) {
      const base = parseFloat(getComputedStyle(list[0]).fontSize);
      list.forEach(el => { el.style.fontSize = (base * k * 0.995) + 'px'; });
    }
  });
}
function rrMeasure(){
  const root = document.getElementById('root'); root.style.width = '1080px'; root.style.height = '1920px';
  const o = root.getBoundingClientRect(), out = [];
  document.querySelectorAll('[data-box]').forEach(el => {
    const kind = el.dataset.box, tight = (kind === 'text' || kind === 'caption');
    const r = tight ? rrRange(el).getBoundingClientRect() : el.getBoundingClientRect();
    const b = el.closest('.beat');
    out.push({id: el.id || null, kind, beat: b ? b.id : null, t0: Number(el.dataset.t0), t1: Number(el.dataset.t1),
      readable: el.dataset.readable === '1', style: el.dataset.style || '', color: el.dataset.color || '', text: tight ? el.textContent.trim().slice(0, 90) : '',
      x: Math.round(r.left - o.left), y: Math.round(r.top - o.top), w: Math.round(r.width), h: Math.round(r.height)});
  });
  const pre = document.createElement('pre'); pre.id = 'rr-boxes'; pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}
"""


def safe_overlay():
    bands = [(0, 0, W, 220), (0, 1470, W, 450), (0, 220, 35, 1250), (W - 35, 220, 35, 1250), (W - 100, 1155, 100, 315)]
    divs = "".join(f'<div style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"></div>' for x, y, w, h in bands)
    seam = '<div style="left:0;top:959px;width:1080px;height:3px;background:#2a7fff;outline:none"></div>'
    return f'<div class="safe-guide" data-layout-ignore>{divs}{seam}</div>'


def build_html(*, title, css, fontface, fonts_load, total, beats_html, captions_html, tween_js, init_js, gsap_src,
               overlay=False, under_html="", motion=None, overlays_html=""):
    """motion (engine/motion): {"script", "css", "defs", "top", "vignette"}. The picture (paper, speaker, panel, beats)
    goes inside #mvT (transitions), the speaker <video> alone inside #mvCam (camera rig); captions stay outside."""
    fl = json.dumps(fonts_load)
    mv = motion or {}
    mv_script = f'<script src="{esc(mv["script"])}"></script>' if mv.get("script") else ""
    # the plate <video> sits alone in .mv-vid; behind-head words and the live cut-out (its own .mv-vid) ride the camera
    cam_open, cam_close = (('<div id="mvCam" data-layout-allow-overflow><div class="mv-vid">',
                            '</div>' + mv.get("behind", "") + '</div>') if mv else ("", ""))
    vig = '<div id="mvVig"></div>' if mv.get("vignette") else ""
    t_open, t_close = ('<div id="mvT" data-layout-allow-overflow>', mv.get("top", "") + '</div>') if mv else ("", "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width={W}, height={H}">
<title>{esc(title)}</title>
<script src="{esc(gsap_src)}"></script>
{mv_script}
<style>
{fontface}
{css}
{mv.get("css", "")}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="{W}" data-height="{H}" data-duration="{total}">
{mv.get("defs", "")}
{t_open}{under_html}
<div id="sp" data-layout-allow-overflow><div id="spmove" data-layout-allow-overflow>{cam_open}<video id="aroll" src="assets/aroll.mp4" playsinline data-start="0" data-duration="{total}" data-track-index="0" data-has-audio="true"></video>{cam_close}</div>{vig}</div>
<div id="panel"></div>
{beats_html}{t_close}
{overlays_html}
{captions_html}
{safe_overlay() if overlay else ""}
</div>
<script>
{RUNTIME}
(async function () {{
  try {{ await Promise.all({fl}.map(f => document.fonts.load(f))); await document.fonts.ready; }} catch (e) {{}}
  rrFitAll();
  if (RR_MEASURE) {{ rrMeasure(); return; }}
{init_js}
  const tl = gsap.timeline({{ paused: true }});
{tween_js}
  window.__timelines["main"] = tl;
}})();
</script>
</body>
</html>
"""
