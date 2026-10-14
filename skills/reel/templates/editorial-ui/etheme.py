"""Design tokens for editorial-ui, read from brand.json (global ~/.reel-room/brand.json, then <project>/brand.json),
overridable in project.json "editorial.tokens". Nothing brand-specific lives anywhere else in this template.

brand.json keys used (all optional):
  colors.set    the coloured set plate (default: colors.accent, deepened 22%)
  colors.cream  headline + card paper (default: colors.bg)
  colors.gold   italic accents, rules, the cover frame (default: #D9B45A)
  colors.ink    card text, subtitle pill (default: colors.ink)
  fonts.serif / fonts.ui / fonts.mono   (default Playfair Display / DM Sans / JetBrains Mono, bundled in fonts/)
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED = {
    "Playfair Display": [("PlayfairDisplay.woff2", "normal", "400 900"), ("PlayfairDisplay-Italic.woff2", "italic", "400 900")],
    "DM Sans": [("DMSans.woff2", "normal", "100 1000")],
    "JetBrains Mono": [("JetBrainsMono.woff2", "normal", "100 800")],
}


def hex_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_hex(c):
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in c)


def mix(a, b, t):
    """a -> b by t (0..1), hex in, hex out."""
    ca, cb = hex_rgb(a), hex_rgb(b)
    return rgb_hex([x + (y - x) * t for x, y in zip(ca, cb)])


def rgba(h, a):
    r, g, b = hex_rgb(h)
    return f"rgba({r},{g},{b},{a})"


def tokens(brand, cfg):
    c, f = brand.get("colors", {}), brand.get("fonts", {})
    over = {k: v for k, v in (cfg.get("tokens") or {}).items() if v}
    accent = c.get("accent", "#7A1E2E")
    t = {
        "set": c.get("set") or mix(accent, "#000000", 0.22),
        "cream": c.get("cream") or c.get("bg", "#F6F2EE"),
        "gold": c.get("gold") or "#D9B45A",
        "ink": c.get("ink", "#1D1214"),
        "flag": "#C8485C",
    }
    t.update(over)
    t.setdefault("set_glow", None)
    t["set_glow"] = t.get("set_glow") or mix(t["set"], accent if accent != t["set"] else "#FFFFFF", 0.55 if accent != t["set"] else 0.12)
    t["set_edge"] = t.get("set_edge") or mix(t["set"], "#000000", 0.5)
    t["pill"] = mix(t["set"], "#000000", 0.72)
    fonts = cfg.get("fonts", {})
    t["serif"] = f.get("serif") or fonts.get("serif", "Playfair Display")
    t["ui"] = f.get("ui") or fonts.get("ui", "DM Sans")
    t["mono"] = f.get("mono") or fonts.get("mono", "JetBrains Mono")
    return t


def luminance(h):
    r, g, b = [v / 255 for v in hex_rgb(h)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def scheme(t, cfg, key):
    """One set colourway: {plate, glow, edge, type, accent, light} for palette `key` ("brand" = the brand set colour).
    Type colour flips automatically when the configured one would not reach 3:1 on the plate (WCAG large text:
    headlines are 120 px and up)."""
    pal = cfg.get("palette", {})
    p = dict(pal.get(key) or {})
    if key not in pal:
        raise SystemExit(f"unknown set colour '{key}'. Palette: {sorted(pal)}")
    plate = p.get("plate") or t["set"]
    typ = p.get("type") or t["cream"]
    acc = p.get("accent") or t["gold"]
    if contrast(typ, plate) < 3.0:
        typ = t["ink"] if contrast(t["ink"], plate) > contrast(t["cream"], plate) else t["cream"]
    light = luminance(plate) > 0.35
    glow = p.get("glow") or (mix(plate, "#FFFFFF", 0.32) if light else mix(plate, t["set_glow"] if key == "brand" else "#FFFFFF",
                                                                          0.55 if key == "brand" else 0.10))
    edge = p.get("edge") or mix(plate, "#000000", 0.22 if light else 0.5)
    return {"key": key, "plate": plate, "glow": glow, "edge": edge, "type": typ, "accent": acc, "light": light}


def fontface(t, project_dir, warn=print):
    """Copy the bundled fonts into <project>/assets/fonts and return @font-face CSS (offline rendering)."""
    out = os.path.join(project_dir, "assets", "fonts")
    os.makedirs(out, exist_ok=True)
    css = []
    for fam in dict.fromkeys((t["serif"], t["ui"], t["mono"])):
        files = BUNDLED.get(fam)
        if not files:
            warn(f"font '{fam}' is not bundled with editorial-ui; drop a woff2 in templates/editorial-ui/fonts or use the defaults")
            continue
        for name, style, weight in files:
            shutil.copyfile(os.path.join(HERE, "fonts", name), os.path.join(out, name))
            css.append(f"@font-face{{font-family:'{fam}';src:url('assets/fonts/{name}') format('woff2');"
                       f"font-weight:{weight};font-style:{style};font-display:block}}")
    return "\n".join(css)


def fonts_load(t):
    return [f'900 200px "{t["serif"]}"', f'italic 700 200px "{t["serif"]}"', f'600 42px "{t["ui"]}"',
            f'700 30px "{t["ui"]}"', f'500 26px "{t["mono"]}"']


def serif(t):
    return f"'{t['serif']}','Bodoni Moda','Didot',Georgia,serif"


def ui(t):
    return f"'{t['ui']}',system-ui,-apple-system,'Segoe UI',sans-serif"


def mono(t):
    return f"'{t['mono']}',ui-monospace,Menlo,monospace"
