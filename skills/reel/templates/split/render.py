#!/usr/bin/env python3
"""render.py <project> [--safe] [--n N] [--no-compose]    compose -> lint (0 errors) -> render renders/<slug>-vN.mp4
render.py snap <project> <t> [<t> ...]                 still PNGs of the composition at cut times (snapshots/)
render.py lint <project> [--no-compose]                compose first (so index.html exists), then lint only

project.json "sound": {"cues": [...]} (file SFX on cut times, see soundcues.py): after the render the cues are mixed
under the voice into renders/<slug>-vN.mp4 and the plain voice render is kept as renders/<slug>-vN-voiceonly.mp4.
--safe renders a draft with the safe-zone guide painted on (renders/<slug>-safe.mp4), then rebuilds the clean index.html.
HyperFrames is pinned. Lint runs as `npx --yes hyperframes@0.8.34 lint` from the project folder (0 errors required);
render runs `npx --yes hyperframes@0.8.34 render -o renders/<slug>-vN.mp4 --quality high`.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compose  # noqa: E402

HF = ["npx", "--yes", "hyperframes@0.8.34"]
if os.name == "nt":
    HF = ["npx.cmd", "--yes", "hyperframes@0.8.34"]


def run(args, cwd, quiet=False):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    if not quiet:
        print(out[-1500:])
    return p.returncode, out


def lint(project):
    code, out = run(HF + ["lint", "--json"], project, quiet=True)
    try:
        data = json.loads(out[out.index("{"):])
        errs = data.get("errorCount", data.get("errors", 0))
        errs = len(errs) if isinstance(errs, list) else errs
        warns = data.get("warningCount", data.get("warnings", 0))
        warns = len(warns) if isinstance(warns, list) else warns
        if not errs and code != 0:
            errs = 1
        return int(errs or 0), int(warns or 0), out
    except Exception:  # noqa: BLE001
        m = re.search(r"(\d+) error\(s\), (\d+) warning", out)
        if m:
            return int(m.group(1)), int(m.group(2)), out
        return (1 if code else 0), 0, out


def short_findings(raw, severity=None):
    """One line per finding: `code (severity): message`. Works on the --json output of hyperframes lint."""
    try:
        data = json.loads(raw[raw.index("{"):])
    except Exception:  # noqa: BLE001
        return raw[-600:]
    lines = []
    for f in data.get("findings", []):
        if severity and f.get("severity") != severity:
            continue
        lines.append(f"  {f.get('severity', '?'):7} {f.get('code')}: {str(f.get('message', ''))[:110]}")
    return "\n".join(lines)


def next_version(project, slug):
    """Next free N: scans renders/ AND work/**/ (old versions get moved there) for <slug>-vN*.mp4."""
    pat = re.compile(rf"{re.escape(slug)}-v(\d+)(?!\d)")
    used = [0]
    for sub in ("renders", "work"):
        for root, _dirs, files in os.walk(os.path.join(project, sub)):
            for f in files:
                m = pat.match(f)
                if m and f.endswith(".mp4"):
                    used.append(int(m.group(1)))
    os.makedirs(os.path.join(project, "renders"), exist_ok=True)
    return max(used) + 1


def prep_media(project):
    """Render prep: every video the composition loads becomes SDR bt709 with a keyframe every 30 frames (engine/hdr.py).
    An HLG-tagged plate makes HyperFrames drop the alpha plane of every cut-out layer in the real render."""
    eng = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine")
    if eng not in sys.path:
        sys.path.insert(0, eng)
    import hdr
    try:
        return hdr.fix_project(project)
    except Exception as e:  # noqa: BLE001  a failed retag must not block the render; QA hdr_alpha still gates it
        print(f"  WARN render prep (hdr.py) failed: {e}")
        return []


PROG = re.compile(r"(\d{1,3})%\s+(.+)")
NOISE = re.compile(r"^\[(INFO|WARN|DEBUG)\]|Render:trace|\x1b\[\?25")


def render_to(project, rel_out, quality):
    """Run `hyperframes render` quietly: one progress line, full log kept in renders/.render.log."""
    t = time.time()
    os.makedirs(os.path.join(project, "renders"), exist_ok=True)
    prep_media(project)
    # --sdr: an iPhone A-roll is often HLG (HDR). HyperFrames then auto-switches to its HDR layered composite, which
    # draws the native video layers OVER the DOM (no captions, no cards, no card clip-path) and writes 10-bit HEVC.
    # Reels are SDR; Chrome tone-maps the HLG clip exactly as the snapshots show it.
    # screenshot capture (as gallery.py) so the frames match `render.py snap`.
    env = dict(os.environ, PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS="180000", PRODUCER_PLAYER_READY_TIMEOUT_MS="180000")
    proc = subprocess.Popen(HF + ["render", "-o", rel_out, "--quality", quality, "--sdr", "--experimental-fast-capture=false"],
                            cwd=project, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
    log, last, tty = [], -1, sys.stdout.isatty()
    buf = ""
    while True:
        ch = proc.stdout.read(1)
        if not ch:
            break
        if ch not in "\r\n":
            buf += ch
            continue
        line, buf = buf, ""
        log.append(line)
        m = PROG.search(line)
        if m:
            pct = int(m.group(1))
            if tty:
                print(f"\r  render {pct:3d}%  {m.group(2)[:40]:<40}", end="", flush=True)
            elif pct // 20 != last // 20 or pct == 100:
                print(f"  render {pct}% {m.group(2)[:40]}", flush=True)
            last = pct
    proc.wait()
    if tty and last >= 0:
        print()
    dt = time.time() - t
    with open(os.path.join(project, "renders", ".render.log"), "w") as f:
        f.write("\n".join(log))
    if proc.returncode != 0 or not os.path.exists(os.path.join(project, rel_out)):
        tail = [l for l in log if l.strip() and not NOISE.search(l)][-15:]
        print("\n".join(tail))
        raise SystemExit(f"render failed after {dt:.0f}s (full log: renders/.render.log)")
    return dt, "\n".join(log)


def motion_sfx_on(project, pj):
    if pj.get("motion") is False or not os.path.exists(os.path.join(project, "work", "motion_plan.json")):
        return False
    import motionlayer
    return motionlayer.M.config(pj)["sfx"] != "off"


def cmd_render(argv):
    project = os.path.abspath([a for a in argv if not a.startswith("--") and not a.isdigit()][0])
    pj = json.load(open(os.path.join(project, "project.json"))) if os.path.exists(os.path.join(project, "project.json")) else {}
    slug = pj.get("slug") or os.path.basename(project)
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else None
    if "--no-compose" not in argv:
        compose.compose(project, overlay=False)
    errs, warns, out = lint(project)
    print(f"lint: {errs} error(s), {warns} warning(s)")
    if errs:
        print(short_findings(out, "error"))
        raise SystemExit("lint has errors; fix before rendering")
    if "--safe" in argv:
        compose.compose(project, overlay=True, do_measure=False)
        dt, _ = render_to(project, f"renders/{slug}-safe.mp4", "draft")
        print(f"safe-zone guide render: renders/{slug}-safe.mp4 ({dt:.0f}s)")
        compose.compose(project, overlay=False, do_measure=False)
        return
    ver = n or next_version(project, slug)
    rel = f"renders/{slug}-v{ver}.mp4"
    dt, out = render_to(project, rel, "high")
    mb = os.path.getsize(os.path.join(project, rel)) / 1e6
    print(f"rendered {os.path.join(project, rel)} ({mb:.1f} MB) in {dt:.0f}s")
    if (pj.get("sound") or {}).get("cues") or motion_sfx_on(project, pj):   # SFX: mixed under the voice, voice-only copy kept
        import soundcues
        rep, vo = soundcues.apply(project, rel)
        print(f"sound cues mixed: {rep['mix']['lufs']:.1f} LUFS, true peak {rep['mix']['tp']:.1f} dBTP, "
              f"SFX peak {rep['sfx_peak_dbfs']} dBFS; voice-only render {vo}")
    print(json.dumps({"ok": True, "file": os.path.join(project, rel), "seconds": round(dt, 1), "lint": {"errors": errs, "warnings": warns}}))


def cmd_snap(argv):
    project = os.path.abspath(argv[0])
    times = ",".join(argv[1:])
    if not times:
        raise SystemExit("usage: render.py snap <project> <t> [<t> ...]")
    shutil.rmtree(os.path.join(project, "snapshots"), ignore_errors=True)
    code, out = run(HF + ["snapshot", "--at", times, "--no-end"], project, quiet=True)
    print(out[-800:])
    print(os.path.join(project, "snapshots"))


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == "snap":
        return cmd_snap(argv[1:])
    if argv[0] == "lint":
        proj = os.path.abspath([a for a in argv[1:] if not a.startswith("--")][0])
        if "--no-compose" not in argv:
            compose.compose(proj, overlay=False, do_measure=False)
        e, w, out = lint(proj)
        print(f"lint: {e} error(s), {w} warning(s)")
        if e or w:
            print(short_findings(out))
        raise SystemExit(1 if e else 0)
    cmd_render(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
