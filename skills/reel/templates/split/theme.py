"""Brand loading, font resolution and the stylesheet for the split template. No brand value lives anywhere else."""
import json
import os
import re
import shutil
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~/.reel-room")
EXAMPLE_BRAND = {
    "name": "Your Name", "handle": "yourhandle",
    "colors": {"bg": "#F4F1EC", "ink": "#0C0C0F", "accent": "#1B8A68", "accent2": "#E2F5EA",
               "highlight": "#FAE67A", "alert": "#C8323F"},
    "fonts": {"display": "Inter Tight", "body": "Inter", "hand": "Caveat"},
    "cta": {"keyword": "AGENT", "text": "Comment AGENT"}, "logo": None,
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def load_brand(project_dir):
    brand = json.loads(json.dumps(EXAMPLE_BRAND))
    for p in (os.path.join(HOME, "brand.json"), os.path.join(project_dir, "brand.json")):
        if os.path.exists(p):
            user = json.load(open(p))
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(brand.get(k), dict):
                    brand[k].update(v)
                else:
                    brand[k] = v
    return brand


def hex_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba(h, a):
    r, g, b = hex_rgb(h)
    return f"rgba({r},{g},{b},{a})"


def _slug(family):
    return re.sub(r"[^A-Za-z0-9]", "", family)


def _google_font(family, dest, italic=False):
    """Fetch a latin woff2 for `family` from Google Fonts into dest (cached). Returns weight range string or None."""
    specs = ("ital@1", "ital,wght@1,400", "ital,wght@1,100..900") if italic else ("wght@100..900", "wght@400;600;800;900", "")
    for spec in specs:
        url = "https://fonts.googleapis.com/css2?family=" + family.replace(" ", "+") + (":" + spec if spec else "")
        try:
            css = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=15).read().decode()
        except Exception:
            continue
        blocks = re.split(r"/\*\s*([\w-]+)\s*\*/", css)
        latin = None
        for i in range(1, len(blocks) - 1, 2):
            if blocks[i] == "latin":
                latin = blocks[i + 1]
        if not latin:
            continue
        m = re.search(r"url\((https://[^)]+\.woff2)\)", latin)
        if not m:
            continue
        data = urllib.request.urlopen(urllib.request.Request(m.group(1), headers={"User-Agent": UA}), timeout=30).read()
        with open(dest, "wb") as f:
            f.write(data)
        if italic:
            return "100 900" if "100..900" in spec else "400"
        return "100 900" if "100..900" in spec else "400 900"
    return None


def resolve_fonts(brand, project_dir, warn, italic=()):
    """Copy/fetch every brand font into <project>/assets/fonts (plus the italic cut of each family in `italic`).
    Returns the @font-face CSS."""
    out_dir = os.path.join(project_dir, "assets", "fonts")
    os.makedirs(out_dir, exist_ok=True)
    cache = os.path.join(HOME, "cache", "fonts")
    os.makedirs(cache, exist_ok=True)
    css = []
    for family in dict.fromkeys(brand["fonts"].values()):
        name = _slug(family) + ".woff2"
        dest = os.path.join(out_dir, name)
        weights = "100 900"
        local = os.path.join(HERE, "fonts", name)
        cached = os.path.join(cache, name)
        if os.path.exists(local):
            shutil.copyfile(local, dest)
            if family == "Caveat":
                weights = "400 700"
        elif os.path.exists(cached):
            shutil.copyfile(cached, dest)
        else:
            w = _google_font(family, cached)
            if not w:
                warn(f"font '{family}' not found locally and Google Fonts was unreachable; using a system fallback")
                continue
            shutil.copyfile(cached, dest)
            weights = w
        css.append(f"@font-face{{font-family:'{family}';src:url('assets/fonts/{name}') format('woff2');"
                   f"font-weight:{weights};font-style:normal;font-display:block}}")
    for family in italic:
        name = _slug(family) + "-Italic.woff2"
        dest, cached = os.path.join(out_dir, name), os.path.join(cache, name)
        weights = "400"
        if not os.path.exists(cached):
            w = _google_font(family, cached, italic=True)
            if not w:
                warn(f"italic of '{family}' not found; the browser will slant the upright cut")
                continue
            weights = w
        shutil.copyfile(cached, dest)
        css.append(f"@font-face{{font-family:'{family}';src:url('assets/fonts/{name}') format('woff2');"
                   f"font-weight:{weights};font-style:italic;font-display:block}}")
    return "\n".join(css)


def fam(name):
    return f"'{name}',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif"


def stylesheet(brand, full_style="pill"):
    c, f = brand["colors"], brand["fonts"]
    scrim_css = (f""".cap.full.scrim .pill{{background:radial-gradient(ellipse at center,{rgba(c['ink'], .66)} 0%,{rgba(c['ink'], .5)} 55%,{rgba(c['ink'], 0)} 100%);
  padding:26px 70px;border-radius:0;text-shadow:0 2px 10px rgba(0,0,0,.5)}}""" if full_style == "scrim" else "")
    return f"""
:root{{--bg:{c['bg']};--ink:{c['ink']};--accent:{c['accent']};--accent2:{c['accent2']};--hl:{c['highlight']};--alert:{c['alert']};
--fd:{fam(f['display'])};--fb:{fam(f['body'])};--fh:{fam(f['hand'])};
--soft:color-mix(in srgb,var(--ink) 58%,var(--bg));--faint:color-mix(in srgb,var(--ink) 30%,var(--bg));
--line:color-mix(in srgb,var(--ink) 9%,transparent);--shadow:0 26px 60px {rgba(c['ink'], .13)},0 4px 14px {rgba(c['ink'], .06)}}}
html,body{{margin:0;padding:0;background:{c['ink']}}}
*{{box-sizing:border-box}}
#root{{position:relative;width:100%;height:100%;overflow:hidden;background:var(--bg);font-family:var(--fb);color:var(--ink)}}
#sp{{position:absolute;left:0;top:0;width:1080px;height:1920px;overflow:hidden;z-index:1}}
#spmove{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
#aroll{{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover}}
/* backface-visibility makes HyperFrames pick its baseline capture path (the experimental drawElement path shows overlays one frame late at cuts) */
#panel{{position:absolute;left:0;top:0;width:1080px;height:960px;z-index:4;
  background:linear-gradient(180deg,var(--bg) 0%,color-mix(in srgb,var(--bg) 93%,#6b5d3a) 100%)}}
.beat{{position:absolute;left:0;top:0;width:1080px;height:960px;z-index:5;overflow:hidden;opacity:0;visibility:hidden}}
.abs{{position:absolute}}
.nw{{white-space:nowrap}}
.cap{{position:absolute;left:0;width:1080px;z-index:20;display:flex;justify-content:center;opacity:0;visibility:hidden}}
.cap.split{{top:996px}}
.cap.full{{top:1250px}}
.cap .pill{{font:800 54px/1 var(--fd);letter-spacing:-.01em;word-spacing:.03em;color:#fff;background:{rgba(c['ink'], .82)};padding:13px 24px 14px;
  border-radius:16px;white-space:nowrap}}
.cap.full .pill{{font-size:64px;padding:15px 28px 16px;border-radius:18px}}
.cap.full.shadow .pill{{background:none;padding:0;font-size:68px;text-shadow:0 3px 18px rgba(0,0,0,.65),0 1px 3px rgba(0,0,0,.55)}}
{scrim_css}
/* hook + cta card */
.card-acc{{display:inline-block;background:var(--accent);border-radius:34px;text-align:center;padding:40px 40px 42px;
  box-shadow:0 30px 60px {rgba(c['accent'], .28)},0 6px 18px {rgba(c['ink'], .1)}}}
.card-acc .l{{display:block;width:max-content;margin:0 auto;white-space:nowrap;font:900 104px/1.02 var(--fd);letter-spacing:-.025em;word-spacing:.05em;
  text-transform:uppercase;color:#fff}}
.card-acc .l.l2{{color:var(--accent2)}}
.centerrow{{position:absolute;left:0;width:1080px;display:flex;justify-content:center}}
/* polaroids */
.pol{{position:absolute;width:340px;height:272px;background:#fff;padding:14px 14px 0;border-radius:4px;
  box-shadow:0 14px 32px {rgba(c['ink'], .2)},0 2px 6px {rgba(c['ink'], .12)}}}
.pol .ph{{width:312px;height:196px;background-size:cover;background-position:center}}
.pol .cp{{display:flex;align-items:center;justify-content:center;gap:10px;height:62px;font:600 36px/1 var(--fh);color:var(--ink);white-space:nowrap}}
.pol .cp b{{font-weight:600;color:var(--alert)}}
/* number card */
.numwrap{{position:absolute;left:0;width:1080px;display:flex;flex-direction:column;align-items:center}}
.num .n{{font:900 300px/230px var(--fd);height:230px;letter-spacing:-.04em;color:var(--accent);text-align:center;white-space:nowrap}}
.num .t{{font:900 100px/1 var(--fd);letter-spacing:-.03em;color:var(--ink);text-transform:uppercase;text-align:center;white-space:nowrap;margin-top:34px}}
.num .s{{font:600 38px/1.2 var(--fb);color:var(--soft);text-align:center;white-space:nowrap;letter-spacing:-.005em;margin-top:24px}}
/* generic white card */
.card{{position:absolute;background:#fff;border-radius:40px;box-shadow:var(--shadow)}}
/* table */
.tbl .hd{{position:absolute;left:0;right:0;top:34px;height:58px;padding:0 30px;display:flex;align-items:center;
  font:700 22px/1 var(--fb);letter-spacing:.16em;color:var(--soft);text-transform:uppercase}}
.tbl .hd span:first-child{{width:330px}}
.tbl .hdline{{position:absolute;left:30px;right:30px;top:94px;height:3px;background:var(--ink)}}
.tbl .row{{position:absolute;left:18px;right:18px;height:102px;display:flex;align-items:center;padding:0 12px;border-bottom:2px solid var(--line);border-radius:14px}}
.tbl .row .a{{width:330px;font:800 42px/1 var(--fd);letter-spacing:-.02em;color:var(--ink);white-space:nowrap}}
.tbl .row .b{{font:500 37px/1 var(--fb);color:var(--soft);white-space:nowrap}}
.tbl .rowhl{{position:absolute;left:0;top:0;right:0;bottom:0;background:var(--hl);border-radius:14px;opacity:0}}
.tbl .row .a,.tbl .row .b{{position:relative}}
.tag{{position:absolute;background:var(--alert);color:#fff;font:800 25px/1 var(--fd);letter-spacing:.06em;text-transform:uppercase;
  padding:11px 18px 12px;border-radius:999px;white-space:nowrap;box-shadow:0 8px 20px {rgba(c['alert'], .35)}}}
/* calendar */
.cal .ttl{{font:900 72px/1 var(--fd);letter-spacing:-.03em;text-transform:uppercase;text-align:center;width:1080px;white-space:nowrap}}
.cal .cell{{position:absolute;width:84px;height:84px;border-radius:16px;background:#fff;box-shadow:0 3px 10px {rgba(c['ink'], .07)};
  display:flex;align-items:center;justify-content:center;font:800 34px/1 var(--fd);color:var(--faint)}}
.cal .cell .on{{position:absolute;inset:0;border-radius:16px;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;opacity:0}}
.cal .cell .on.soft{{background:color-mix(in srgb,var(--accent) 38%,#fff)}}
.pillx{{position:relative;display:inline-flex;align-items:center;justify-content:center;padding:0 38px;height:68px;border-radius:999px;
  font:800 38px/1 var(--fd);letter-spacing:-.01em;white-space:nowrap}}
.pillx.good{{background:var(--accent2);color:var(--accent)}}
.pillx.bad{{background:color-mix(in srgb,var(--alert) 13%,#fff);color:var(--alert)}}
.pillx .strike{{position:absolute;left:30px;right:30px;top:50%;height:7px;margin-top:-3px;border-radius:4px;background:var(--alert);opacity:0}}
/* checklist */
.chk .ttl{{position:absolute;left:40px;top:32px;font:800 40px/1 var(--fd);letter-spacing:-.02em}}
.chk .row{{position:absolute;left:40px;right:40px;height:92px;border-top:2px solid var(--line);display:flex;align-items:center;gap:26px}}
.chk .ring{{position:relative;width:56px;height:56px;border-radius:50%;border:4px solid var(--faint);flex:none}}
.chk .fill{{position:absolute;inset:-4px;border-radius:50%;background:var(--accent);opacity:0;display:flex;align-items:center;justify-content:center}}
.chk .fill svg{{width:30px;height:30px}}
.chk .lbl{{font:800 42px/1 var(--fd);letter-spacing:-.02em;color:var(--faint);white-space:nowrap}}
.chk .row.done .lbl{{color:var(--ink)}}
.chk .row.done .fill{{opacity:1}}
.chk .row.done .ring{{border-color:transparent}}
/* two-path */
.two .rw{{position:absolute;left:40px;right:40px;height:150px;display:flex;align-items:center;gap:22px}}
.two .cond{{height:78px;padding:0 28px;border-radius:999px;display:flex;align-items:center;font:700 34px/1 var(--fb);white-space:nowrap}}
.two .cond.a{{background:var(--accent2);color:var(--accent)}}
.two .cond.b{{background:color-mix(in srgb,var(--alert) 13%,#fff);color:var(--alert)}}
.two .arr{{font:800 50px/1 var(--fd);color:var(--faint)}}
.two .res{{font:900 52px/1 var(--fd);letter-spacing:-.02em;text-transform:uppercase;white-space:nowrap;color:var(--ink)}}
.two .sep{{position:absolute;left:40px;right:40px;height:2px;background:var(--line)}}
/* image + pills */
.imgbox{{position:absolute;overflow:hidden}}
.imgbox .im{{position:absolute;inset:0;background-size:cover;background-position:center}}
.imgpill{{position:absolute;left:0;width:1080px;display:flex;justify-content:center}}
.imgpill .in{{background:#fff;border-radius:999px;padding:0 36px;height:84px;display:flex;align-items:center;white-space:nowrap;
  font:800 44px/1 var(--fd);letter-spacing:-.02em;color:var(--ink);box-shadow:0 14px 34px {rgba(c['ink'], .28)}}}
.imgpill .in b{{font-weight:800;color:var(--accent);margin-left:.28em}}
.strikepill{{background:#fff;border-radius:999px;box-shadow:var(--shadow);padding:0 54px;height:132px;display:flex;align-items:center;position:relative;
  font:800 66px/1 var(--fd);letter-spacing:-.02em;white-space:nowrap}}
.strikepill .ln{{position:absolute;left:36px;right:36px;top:50%;height:11px;margin-top:-5px;background:var(--alert);border-radius:6px;opacity:0}}
.sub{{font:700 40px/1.2 var(--fb);color:var(--soft);text-align:center;white-space:nowrap}}
.vid{{position:absolute;object-fit:cover}}
.vwrap{{position:absolute;overflow:hidden}}
/* big stat */
.statwrap{{position:absolute;left:0;width:1080px;display:flex;flex-direction:column;align-items:center}}
.statwrap .lbl{{font:900 50px/1 var(--fd);letter-spacing:.04em;text-transform:uppercase;color:var(--ink);white-space:nowrap;height:56px}}
.statwrap .row{{display:flex;align-items:baseline;justify-content:center;gap:22px;height:300px;margin-top:20px}}
.statwrap .pre{{font:900 96px/1 var(--fd);letter-spacing:-.03em;text-transform:uppercase;color:var(--ink);white-space:nowrap}}
.statwrap .v{{display:inline-block;font:900 330px/250px var(--fd);letter-spacing:-.05em;color:var(--accent);white-space:nowrap}}
.statwrap .unit{{font:700 40px/1 var(--fb);color:var(--soft);white-space:nowrap}}
.statwrap .vbox{{position:relative;display:inline-block}}
.statwrap .v.ghost{{position:absolute;left:0;top:0;opacity:.09}}
.stat-tag{{font-size:34px;padding:16px 28px 17px}}
.num .k{{font:800 28px/1 var(--fb);letter-spacing:.22em;text-transform:uppercase;color:var(--soft);margin-bottom:18px;white-space:nowrap}}
.safe-guide{{position:absolute;inset:0;z-index:99;pointer-events:none}}
.safe-guide div{{position:absolute;background:rgba(255,40,40,.28);outline:2px solid rgba(255,40,40,.7)}}
"""
