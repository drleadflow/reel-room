"""Floating Cards: page CSS (brand tokens from brand.json; no hardcoded brand colours)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stylekit"))
import kit  # noqa: E402


def css(proj):
    c, f = proj.colors, proj.fonts
    ink, acc, gold, bg = c["ink"], c["accent"], c["highlight"], c["bg"]
    alert = c.get("alert", acc)
    serif = f.get("serif", f["display"])
    return f"""
:root{{--ink:{ink};--acc:{acc};--gold:{gold};--bg:{bg};--alert:{alert};--fd:{kit.fam(f['display'])};--fb:{kit.fam(f['body'])};
--fs:'{serif}',Georgia,serif;--soft:color-mix(in srgb,{ink} 58%,#fff)}}
html,body{{margin:0;padding:0;background:#000}}
*{{box-sizing:border-box}}
#root{{position:relative;width:100%;height:100%;overflow:hidden;background:#000;font-family:var(--fb);color:var(--ink)}}
#aroll{{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover;z-index:1}}
.layer{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:5;pointer-events:none}}
/* card = .kw (home, re-arrange, tumble) > .kf (idle float) > .ksh (contact shadow) + .card (3D fly-in) */
.kw{{position:absolute;visibility:hidden;transform-origin:50% 50%}}
.kf{{position:relative;display:inline-block;transform-origin:50% 50%}}
.ksh{{position:absolute;left:9%;right:9%;bottom:-22px;height:46px;border-radius:50%;opacity:0;
  background:radial-gradient(closest-side,{kit.rgba(ink, .30)},{kit.rgba(ink, .12)} 55%,{kit.rgba(ink, 0)});filter:blur(7px)}}
.el{{position:relative;opacity:0;visibility:hidden;transform-origin:50% 60%}}
.card{{display:flex;align-items:center;gap:22px;padding:22px 36px 22px 22px;border-radius:32px;white-space:nowrap;
  background:linear-gradient(160deg,rgba(255,255,255,.88),rgba(250,246,242,.74));
  -webkit-backdrop-filter:blur(22px) saturate(140%);backdrop-filter:blur(22px) saturate(140%);
  border:1.5px solid rgba(255,255,255,.92);
  box-shadow:0 26px 54px {kit.rgba(ink, .17)},0 3px 10px {kit.rgba(ink, .08)},inset 0 1px 0 #fff}}
.strike{{position:absolute;left:-3%;right:-3%;top:50%;height:9px;margin-top:-4px;border-radius:6px;background:var(--alert);
  transform-origin:0 50%;opacity:0;box-shadow:0 3px 10px {kit.rgba(alert, .4)};z-index:3}}
.ico{{width:88px;height:88px;flex:none;border-radius:25px;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(150deg,color-mix(in srgb,{acc} 82%,#fff),{acc} 60%,color-mix(in srgb,{acc} 80%,#000));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.28),0 6px 14px {kit.rgba(acc, .3)}}}
.ico.gold{{background:linear-gradient(150deg,color-mix(in srgb,{gold} 80%,#fff),{gold} 60%,color-mix(in srgb,{gold} 82%,#000));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.4),0 6px 14px {kit.rgba(gold, .35)}}}
.ico.sm{{width:46px;height:46px;border-radius:14px}}
.tx{{display:flex;flex-direction:column;gap:8px}}
.tt{{font:800 52px/1 var(--fd);letter-spacing:-.02em;word-spacing:.14em;color:var(--ink)}}
.sb{{position:relative;font:500 29px/1.1 var(--fb);color:var(--soft);letter-spacing:-.005em;word-spacing:.04em}}
.sb .ul{{position:absolute;left:0;right:0;bottom:-7px;height:5px;border-radius:3px;background:var(--gold);
  transform-origin:0 50%;transform:scaleX(0);opacity:0}}
.rows{{display:flex;flex-direction:column;gap:12px;margin-top:4px}}
.fr{{display:flex;align-items:center;gap:16px;height:34px;font:600 28px/1 var(--fb);color:var(--ink)}}
.fr .nm{{width:240px}}
.fr i{{display:block;width:290px;height:12px;border-radius:7px;background:{kit.rgba(ink, .11)};overflow:hidden}}
.fr i b{{display:block;height:12px;border-radius:7px;background:var(--acc);transform-origin:0 50%}}
.fr .tk{{display:flex;width:34px;height:34px;border-radius:50%;align-items:center;justify-content:center;color:#fff;
  background:var(--acc);visibility:hidden}}
.fr.slot{{height:0;overflow:hidden;opacity:0;padding:0 16px;margin:0 -16px;border:2.5px dashed {kit.rgba(ink, .28)};
  border-radius:14px;justify-content:space-between}}
.fr.slot .nm{{width:auto;font-weight:700}}
.fr.slot .q{{font:800 30px/1 var(--fd);color:var(--soft)}}
.fr.slot .tk.on{{background:var(--gold);position:absolute;right:16px}}
.panel{{flex-direction:column;align-items:stretch;gap:18px;padding:30px 38px 32px;width:680px}}
.card.hero{{padding:26px 46px 26px 26px;gap:28px;border-radius:38px}}
.card.hero .ico{{width:106px;height:106px;border-radius:30px}}
.card.hero .tt{{font-size:64px}}
.card.hero .sb{{font-size:33px}}
.panel .hdr{{display:flex;align-items:center;gap:22px}}
.panel .rows .fr{{position:relative}}
.chip{{display:flex;align-items:center;gap:14px;padding:12px 30px 13px 14px;border-radius:999px;font:800 36px/1 var(--fd);
  letter-spacing:.02em;color:var(--ink);background:rgba(255,255,255,.88);border:1.5px solid #fff;white-space:nowrap;
  -webkit-backdrop-filter:blur(16px);backdrop-filter:blur(16px);box-shadow:0 16px 36px {kit.rgba(ink, .15)}}}
.status{{flex-direction:column;align-items:center;gap:6px;padding:30px 54px 32px;border-radius:42px;width:680px}}
.status .eb{{font:700 25px/1 var(--fb);letter-spacing:.2em;text-transform:uppercase;color:var(--soft)}}
.status .big{{position:relative;display:block;font:900 176px/1 var(--fd);letter-spacing:-.03em;word-spacing:.06em;color:var(--ink);padding:0 40px;isolation:isolate}}
.status .big .gl{{position:absolute;left:-40px;right:-40px;top:-10px;bottom:-16px;z-index:-1;border-radius:50%;
  background:radial-gradient(closest-side,{kit.rgba(gold, .6)},{kit.rgba(gold, .24)} 55%,{kit.rgba(gold, 0)})}}
.status .big .vv{{display:inline-block}}
.status .unit{{word-spacing:.04em;font:600 29px/1 var(--fb);color:var(--soft);margin-top:-2px}}
.status .row2{{word-spacing:.05em;display:flex;align-items:center;gap:14px;margin-top:16px;padding:14px 26px;border-radius:999px;
  background:{kit.rgba(acc, .1)};font:700 31px/1 var(--fb);color:var(--acc);white-space:nowrap}}
.status .row2 .dot{{width:16px;height:16px;border-radius:50%;background:var(--acc);box-shadow:0 0 0 6px {kit.rgba(acc, .16)}}}
.week{{flex-direction:column;align-items:flex-start;gap:6px;width:288px;padding:24px 28px 26px;border-radius:32px}}
.week .eb{{display:flex;align-items:center;gap:12px;font:700 24px/1 var(--fb);letter-spacing:.18em;text-transform:uppercase;color:var(--soft)}}
.week .eb .ico{{width:48px;height:48px;border-radius:14px}}
.week .n{{font:900 112px/1 var(--fd);letter-spacing:-.03em;color:var(--ink)}}
.week.pick{{border:3px solid var(--gold);box-shadow:0 0 0 8px {kit.rgba(gold, .22)},0 0 60px {kit.rgba(gold, .55)},0 22px 50px {kit.rgba(ink, .16)}}}
.flag{{position:absolute;right:18px;top:-24px;padding:11px 18px 12px;border-radius:999px;background:var(--acc);color:#fff;
  font:800 24px/1 var(--fd);letter-spacing:.08em;text-transform:uppercase;box-shadow:0 8px 20px {kit.rgba(acc, .35)}}}
.title{{position:absolute;left:0;width:1080px;display:flex;flex-direction:column;align-items:center;text-align:center}}
.title .t1{{font:700 60px/1.05 var(--fd);letter-spacing:-.015em;color:var(--ink)}}
.title .t2{{font:900 106px/1 var(--fd);letter-spacing:-.03em;word-spacing:.06em;color:var(--ink);margin-top:6px}}
.title .t3{{font:italic 700 132px/1 var(--fs);letter-spacing:-.01em;color:var(--acc);margin-top:0}}
.title span{{white-space:nowrap;text-shadow:0 2px 24px rgba(255,255,255,.65)}}
.hud{{position:absolute;left:0;width:1080px;display:flex;justify-content:center;gap:14px;visibility:hidden;opacity:0}}
.hd{{position:relative;display:flex;align-items:center;width:60px;height:60px;border-radius:999px;overflow:hidden;
  background:rgba(255,255,255,.86);border:1.5px solid #fff;box-shadow:0 10px 26px {kit.rgba(ink, .14)};
  -webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px)}}
.hd .hn{{flex:none;width:57px;text-align:center;font:800 28px/1 var(--fd);color:var(--soft)}}
.hd .hl{{flex:none;padding-right:22px;font:800 26px/1 var(--fd);letter-spacing:.06em;text-transform:uppercase;color:#fff;
  white-space:nowrap;opacity:0;margin-left:-6px}}
.gcap{{position:absolute;left:0;width:1080px;display:flex;justify-content:center;z-index:30;opacity:0;visibility:hidden}}
.gcap span{{font:800 86px/1 var(--fd);letter-spacing:-.015em;color:#fff;white-space:nowrap;
  text-shadow:0 0 2px {kit.rgba(ink, .5)},0 3px 10px {kit.rgba(ink, .55)},0 0 30px {kit.rgba(ink, .42)},0 0 16px rgba(255,240,214,.55)}}
"""
