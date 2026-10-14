#!/usr/bin/env bash
# Reel Room installer for macOS and Linux. One command:   ./install.sh
#   --yes           answer yes to every install prompt (brew / apt)
#   --no-models     skip the speech models (about 2 GB) for now; `./reel assets` gets them later
#   --skill-only    only (re)install the /reel skill into ~/.claude/skills/reel
#   --copy-skill    copy the skill instead of linking it
# Re-running is safe: finished steps are skipped.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RR_HOME="${REEL_ROOM_HOME:-$HOME/.reel-room}"
VENV="$RR_HOME/venv"
SKILL_SRC="$HERE/skills/reel"
SKILL_DEST="$HOME/.claude/skills/reel"
YES=0; NO_MODELS=""; SKILL_ONLY=0; COPY=0
for a in "$@"; do
  case "$a" in
    --yes|-y) YES=1 ;;
    --no-models) NO_MODELS="--no-models" ;;
    --skill-only) SKILL_ONLY=1 ;;
    --copy-skill) COPY=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown option $a"; exit 2 ;;
  esac
done
T0=$(date +%s)
OS="$(uname -s)"
say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  OK   %s\n' "$*"; }
die()  { printf '\n  STOP %s\n' "$*"; exit 1; }
confirm() {  # confirm "question" -> 0 for yes
  [ "$YES" = 1 ] && return 0
  [ -t 0 ] || return 1
  read -r -p "  $1 [Y/n] " r; [ -z "$r" ] || [[ "$r" =~ ^[Yy] ]]
}
pkg_install() {  # pkg_install <brew name> <apt name> <label>
  if [ "$OS" = "Darwin" ]; then
    command -v brew >/dev/null || die "Homebrew is needed to install $3. Get it at https://brew.sh, then run ./install.sh again."
    confirm "Install $3 with Homebrew (brew install $1)?" || die "$3 is required. Install it, then run ./install.sh again."
    brew install $1 || die "brew install $1 failed"
  elif command -v apt-get >/dev/null; then
    confirm "Install $3 with apt (sudo apt-get install -y $2)?" || die "$3 is required. Install it, then run ./install.sh again."
    sudo apt-get update -qq && sudo apt-get install -y $2 || die "apt-get install $2 failed"
  else
    die "Install $3 with your package manager, then run ./install.sh again."
  fi
}

install_skill() {
  say "Installing the /reel skill for Claude Code"
  mkdir -p "$(dirname "$SKILL_DEST")"
  if [ -L "$SKILL_DEST" ]; then rm "$SKILL_DEST"
  elif [ -e "$SKILL_DEST" ]; then
    BK="$SKILL_DEST.backup-$(date +%Y%m%d-%H%M%S)"; mv "$SKILL_DEST" "$BK"; ok "moved your old skill to $BK"
  fi
  if [ "$COPY" = 1 ]; then cp -R "$SKILL_SRC" "$SKILL_DEST"; else ln -s "$SKILL_SRC" "$SKILL_DEST"; fi
  ok "/reel -> $SKILL_DEST"
}

if [ "$SKILL_ONLY" = 1 ]; then install_skill; exit 0; fi

say "Reel Room installer ($(sed -n 's/.*"label": "\(.*\)".*/\1/p' "$SKILL_SRC/edition.json" | head -1))"
FREE_GB=$(df -Pk "$HOME" | awk 'NR==2 {printf "%d", $4/1048576}')
echo "  free disk: ${FREE_GB} GB (the install uses about 3.5 GB)"
[ "${FREE_GB:-0}" -lt 10 ] && echo "  WARNING: under 10 GB free. Installing anyway; renders need 2 to 5 GB each."

say "1/6 Python 3.11 to 3.13"
PYBIN=""
for v in 3.12 3.11 3.13; do
  if command -v "python$v" >/dev/null; then PYBIN="$(command -v python$v)"; break; fi
done
if [ -z "$PYBIN" ] && command -v python3 >/dev/null; then
  V=$(python3 -c 'import sys;print("%d%02d"%sys.version_info[:2])')
  [ "$V" -ge 311 ] && [ "$V" -le 313 ] && PYBIN="$(command -v python3)"
fi
if [ -z "$PYBIN" ]; then
  pkg_install python@3.12 "python3.12 python3.12-venv" "Python 3.12"
  PYBIN="$(command -v python3.12 || true)"; [ -n "$PYBIN" ] || die "Python 3.12 still not found on PATH; open a new terminal and run ./install.sh again."
fi
ok "$PYBIN ($($PYBIN -V 2>&1))"

say "2/6 ffmpeg and Node 22+"
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || pkg_install ffmpeg ffmpeg "ffmpeg"
ok "ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"
NODE_MAJOR=$(node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')
if [ -z "$NODE_MAJOR" ] || [ "$NODE_MAJOR" -lt 22 ]; then
  if [ "$OS" = "Darwin" ]; then
    pkg_install node@22 "" "Node 22"; brew link --overwrite --force node@22 >/dev/null 2>&1 || true
  else
    echo "  Node 22+ is needed (found: ${NODE_MAJOR:-none})."
    if confirm "Install Node 22 from NodeSource (needs sudo)?"; then
      curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs || die "Node install failed"
    else die "Install Node 22+ (https://nodejs.org or: nvm install 22), then run ./install.sh again."; fi
  fi
fi
ok "node $(node -v)"

say "3/6 Python environment ($VENV) with pinned packages"
mkdir -p "$RR_HOME"
if [ ! -x "$VENV/bin/python" ]; then "$PYBIN" -m venv "$VENV" || die "could not create the venv (on Linux: sudo apt-get install python3.12-venv)"; fi
"$VENV/bin/python" -m pip install --disable-pip-version-check -q --upgrade pip || die "pip upgrade failed (check your internet)"
"$VENV/bin/python" -m pip install --disable-pip-version-check -r "$HERE/requirements.txt" || die "pip install failed (check your internet, then run ./install.sh again)"
ok "packages installed ($(wc -l < "$HERE/requirements.txt" | tr -d ' ') pinned)"

say "4/6 Models, GSAP and HyperFrames (one time; downloads resume if interrupted)"
"$VENV/bin/python" "$SKILL_SRC/tools/reel_cli.py" assets $NO_MODELS || die "a download failed. Run ./install.sh again to resume."

say "5/6 Keys, brand and the /reel skill"
[ -f "$HERE/.env" ] || { cp "$HERE/.env.example" "$HERE/.env"; ok "created .env from .env.example (keys are optional, see the comments inside)"; }
chmod 600 "$HERE/.env" 2>/dev/null || true
if [ ! -e "$RR_HOME/.env" ] || [ -L "$RR_HOME/.env" ]; then ln -sfn "$HERE/.env" "$RR_HOME/.env"; ok "$RR_HOME/.env -> $HERE/.env"; fi
printf '{"repo": "%s", "installed": "%s"}\n' "$HERE" "$(date +%Y-%m-%dT%H:%M:%S)" > "$RR_HOME/install.json"
[ -f "$RR_HOME/brand.json" ] || { "$VENV/bin/python" "$SKILL_SRC/tools/reel_cli.py" setup --defaults >/dev/null && ok "default brand written (run ./reel setup to make it yours)"; }
install_skill

say "6/6 Checking everything"
"$VENV/bin/python" "$SKILL_SRC/tools/reel_cli.py" doctor
RC=$?
T=$(( $(date +%s) - T0 ))
say "Install finished in $((T / 60)) min $((T % 60)) s"
if [ $RC = 0 ]; then
  echo "  Next:  ./reel setup      (your name, handle, colours)"
  echo "         ./reel demo       (renders the sample reel, a few minutes)"
  echo "         then open Claude Code and type /reel"
else
  echo "  Fix the FAIL lines above (each has its exact command), then run ./reel doctor"
fi
exit $RC
