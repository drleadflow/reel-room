"""Kept for older notes and error messages that say `doctor.py`: forwards to `reel doctor` (tools/rr_doctor.py)."""
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    cli = Path(__file__).resolve().parents[1] / "tools" / "reel_cli.py"
    sys.exit(subprocess.call([sys.executable, str(cli), "doctor", *sys.argv[1:]]))
