"""`reel setup`: the brand wizard. Asks name, handle, colours, fonts, call to action and folders, then writes
~/.reel-room/brand.json (the only place brand values live). Every question has a default: press Enter to keep it.

Non-interactive (for scripts, or when Claude writes it for you):
  reel setup --defaults
  reel setup --name "Jane Doe" --handle janedoe --accent "#2457D6" --cta-keyword GUIDE --projects-dir ~/Reels
"""
from __future__ import annotations

import argparse
import colorsys
import json
import re
import sys
from pathlib import Path

import rr_common as R

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
ACCENTS = {"green": "#1B8A68", "red": "#C8323F", "blue": "#2457D6"}


def tint(hex_color: str, light: float = 0.93) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, light, min(s, 0.55))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def luminance(hex_color: str) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def white_contrast(hex_color: str) -> float:
    return 1.05 / (luminance(hex_color) + 0.05)


def ask(prompt: str, default: str, check=None) -> str:
    while True:
        v = input(f"{prompt} [{default}]: ").strip() or default
        err = check(v) if check else None
        if not err:
            return v
        print("  " + err)


def accent_ok(v: str):
    v = ACCENTS.get(v.lower(), v)
    if not HEX.match(v):
        return "use a 6-digit hex like #1B8A68, or green / red / blue"
    if white_contrast(v) < 3.0:
        return f"white text is hard to read on {v} (contrast {white_contrast(v):.1f}); pick a darker colour"
    return None


def build(name, handle, accent, display, body, hand, keyword, cta_text, projects, clips, voice=None) -> dict:
    accent = ACCENTS.get(accent.lower(), accent).upper()
    return {"name": name, "handle": handle.lstrip("@"),
            "colors": {"bg": "#F4F1EC", "ink": "#0C0C0F", "accent": accent, "accent2": tint(accent),
                       "highlight": "#FAE67A", "alert": "#C8323F"},
            "fonts": {"display": display, "body": body, "hand": hand},
            "cta": ({"keyword": keyword.upper(), "text": cta_text or f"Comment {keyword.upper()}"}
                    if keyword and keyword.lower() != "none" else None),
            "logo": None, "projectsDir": projects, "clipsDir": clips, **({"voice": voice} if voice else {})}


def interactive(cur: dict) -> dict:
    print("Brand setup. Press Enter to keep the value in brackets.\n")
    name = ask("Your name as it should appear on cards", cur.get("name", "Your Name"))
    handle = ask("Instagram handle (no @)", cur.get("handle", "yourhandle"))
    accent = ask("Accent colour (hex, or green / red / blue)", cur.get("colors", {}).get("accent", "#1B8A68"),
                 accent_ok)
    f = cur.get("fonts", {})
    print("Fonts: any Google Font name works (they are free, OFL). Keep the defaults if unsure.")
    display = ask("  display font (big titles)", f.get("display", "Inter Tight"))
    body = ask("  body font (captions, cards)", f.get("body", "Inter"))
    hand = ask("  hand font (notes)", f.get("hand", "Caveat"))
    c = cur.get("cta") or {}
    keyword = ask("Call to action keyword for comment-to-DM, or none", c.get("keyword", "none"))
    cta_text = ask("Call to action line", c.get("text", f"Comment {keyword.upper()}")) if keyword != "none" else ""
    projects = ask("Folder for finished projects", cur.get("projectsDir", "~/ReelRoom"))
    clips = ask("Folder where new clips usually land", cur.get("clipsDir", "~/Downloads"))
    voice = input("How you sound, one line (optional, Enter to skip): ").strip() or cur.get("voice")
    return build(name, handle, accent, display, body, hand, keyword, cta_text, projects, clips, voice)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reel setup", description=__doc__.split("\n")[0])
    ap.add_argument("--defaults", action="store_true", help="write the defaults without asking")
    for k in ("name", "handle", "accent", "display", "body", "hand", "cta-keyword", "cta-text", "projects-dir",
              "clips-dir", "voice"):
        ap.add_argument(f"--{k}")
    a = ap.parse_args(argv)
    path = R.HOME / "brand.json"
    cur = R.brand()
    given = any(v for k, v in vars(a).items() if k != "defaults")
    if a.defaults or given or not sys.stdin.isatty():
        c, f = cur.get("cta") or {}, cur.get("fonts", {})
        acc = a.accent or cur.get("colors", {}).get("accent", "#1B8A68")
        err = accent_ok(acc)
        if err:
            raise SystemExit(f"--accent: {err}")
        brand = build(a.name or cur.get("name", "Your Name"), a.handle or cur.get("handle", "yourhandle"), acc,
                      a.display or f.get("display", "Inter Tight"), a.body or f.get("body", "Inter"),
                      a.hand or f.get("hand", "Caveat"), a.cta_keyword or c.get("keyword", "none"),
                      a.cta_text or c.get("text", ""), a.projects_dir or cur.get("projectsDir", "~/ReelRoom"),
                      a.clips_dir or cur.get("clipsDir", "~/Downloads"), a.voice or cur.get("voice"))
    else:
        brand = interactive(cur)
    if "lessons" in cur:
        brand["lessons"] = cur["lessons"]
    R.HOME.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(brand, indent=2) + "\n")
    Path(Path(brand["projectsDir"]).expanduser()).mkdir(parents=True, exist_ok=True)
    print(f"\nSaved {path}:\n" + json.dumps(brand, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
