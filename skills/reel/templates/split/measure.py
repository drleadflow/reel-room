"""Measure every [data-box] element in the composition with the headless Chrome HyperFrames already downloaded."""
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def find_chrome():
    env = os.environ.get("REEL_ROOM_CHROME") or os.environ.get("HYPERFRAMES_CHROME")
    if env and os.path.exists(env):
        return env
    pats = [os.path.expanduser("~/.cache/hyperframes/chrome/**/chrome-headless-shell*"),
            os.path.expanduser("~/.cache/puppeteer/**/chrome-headless-shell*"),
            os.path.expanduser("~/.cache/ms-playwright/**/chrome-headless-shell*"),
            os.path.expanduser("~/AppData/Local/hyperframes/chrome/**/chrome-headless-shell*.exe")]
    for pat in pats:
        for p in sorted(glob.glob(pat, recursive=True), reverse=True):
            if os.path.isfile(p) and os.access(p, os.X_OK) and not p.endswith((".zip", ".json")):
                return p
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return mac if os.path.exists(mac) else None


def measure(index_html, timeout=60):
    """Returns (boxes, error). boxes is None when no browser is available."""
    chrome = find_chrome()
    if not chrome:
        return None, "no Chrome found (run hyperframes doctor)"
    url = Path(os.path.abspath(index_html)).as_uri() + "#measure"
    cmd = [chrome, "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--hide-scrollbars",
           "--window-size=1080,1920", "--virtual-time-budget=6000", "--dump-dom", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return None, f"chrome failed: {e}"
    m = re.search(r'<pre id="rr-boxes">(.*?)</pre>', r.stdout, re.S)
    if not m:
        return None, "measure output missing (page error?) " + r.stderr[-300:]
    return json.loads(html.unescape(m.group(1))), None


if __name__ == "__main__":
    b, err = measure(sys.argv[1])
    print(err or f"{len(b)} boxes")
