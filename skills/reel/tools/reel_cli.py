#!/usr/bin/env python3
"""reel: the Reel Room command line.

  reel doctor            check every dependency and key, print the exact fix for anything missing
  reel setup             brand wizard (name, handle, colours, fonts, call to action, folders)
  reel demo <clip>       turn one clip of you talking (20 to 60 s, vertical) into a finished reel in minutes
  reel try               10 things to say to /reel in Claude Code, to see what it can do
  reel phrases           where the full "say this to get that" list lives
  reel assets            (re)download models, GSAP and the pinned HyperFrames (resumes broken downloads)
  reel run <script> ...  run an engine script with the .env keys loaded (e.g. reel run engine/post.py <project>)
  reel test              run the engine's own test suite (no network, no keys, about 10 s)
  reel version
Most work happens in Claude Code: type /reel and give it your clip's file path.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rr_common as R  # noqa: E402

TRY = Path(__file__).resolve().parent / "try.txt"


def cmd_try(_argv) -> int:
    print("Open Claude Code and type /reel, then try these (one at a time):\n")
    for i, line in enumerate(TRY.read_text().strip().splitlines(), 1):
        print(f"{i:2}. {line}")
    print(f"\nMore phrases: {R.repo_dir() / 'PHRASES.md' if R.repo_dir() else 'PHRASES.md in the repo'}")
    return 0


def cmd_phrases(_argv) -> int:
    r = R.repo_dir()
    print(f"The full phrase list: {r / 'PHRASES.md' if r else 'PHRASES.md in the repo'}  (also: {R.reel_cmd()} try)")
    return 0


def main(argv) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    R.load_env()
    if cmd == "doctor":
        import rr_doctor
        return rr_doctor.main(rest)
    if cmd == "setup":
        import rr_setup
        return rr_setup.main(rest)
    if cmd == "demo":
        import rr_demo
        return rr_demo.main(rest)
    if cmd == "assets":
        import rr_assets
        return rr_assets.main(rest)
    if cmd == "try":
        return cmd_try(rest)
    if cmd == "phrases":
        return cmd_phrases(rest)
    if cmd == "run" and rest:
        import subprocess
        script = R.SK / rest[0] if not Path(rest[0]).is_absolute() else Path(rest[0])
        return subprocess.call([str(R.venv_python()), str(script), *rest[1:]])
    if cmd == "test":
        import subprocess
        rc = 0
        for d in [p for p in ((R.repo_dir() or R.SK) / "tests", R.SK / "templates" / "kit") if p.exists()]:
            print(f"== {d}")
            rc |= subprocess.call([str(R.venv_python()), "-m", "unittest", "discover", "-s", str(d), "-p", "test_*.py"],
                                  cwd=str(d))
        return rc
    if cmd in ("version", "--version"):
        e = R.edition()
        print(f"{e['label']} {e['version']}")
        return 0
    print(f"unknown command {cmd!r}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
