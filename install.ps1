# Reel Room installer for Windows 10/11. One command (in PowerShell, from this folder):
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# Options: -Yes (answer yes to every winget prompt)  -NoModels (skip the 2 GB speech models for now)
#          -SkillOnly (only reinstall the /reel skill)
# Re-running is safe: finished steps are skipped.
param([switch]$Yes, [switch]$NoModels, [switch]$SkillOnly)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$RRHome = if ($env:REEL_ROOM_HOME) { $env:REEL_ROOM_HOME } else { Join-Path $env:USERPROFILE ".reel-room" }
$Venv = Join-Path $RRHome "venv"
$VenvPy = Join-Path $Venv "Scripts\python.exe"
$SkillSrc = Join-Path $Here "skills\reel"
$SkillDest = Join-Path $env:USERPROFILE ".claude\skills\reel"
$T0 = Get-Date

function Say($m) { Write-Host "`n$m" -ForegroundColor White }
function Ok($m) { Write-Host "  OK   $m" }
function Stop-Install($m) { Write-Host "`n  STOP $m" -ForegroundColor Red; exit 1 }
function Confirm-Step($q) {
  if ($Yes) { return $true }
  $r = Read-Host "  $q [Y/n]"
  return ($r -eq "" -or $r -match "^[Yy]")
}
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Winget-Install($id, $label) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Stop-Install "winget is missing. Install $label by hand, then run install.ps1 again." }
  if (-not (Confirm-Step "Install $label with winget ($id)?")) { Stop-Install "$label is required. Install it, then run install.ps1 again." }
  winget install -e --id $id --accept-source-agreements --accept-package-agreements
  Refresh-Path
}
function Install-Skill {
  Say "Installing the /reel skill for Claude Code"
  New-Item -ItemType Directory -Force -Path (Split-Path $SkillDest) | Out-Null
  if (Test-Path $SkillDest) {
    $bk = "$SkillDest.backup-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    Move-Item $SkillDest $bk; Ok "moved your old skill to $bk"
  }
  try { New-Item -ItemType Junction -Path $SkillDest -Target $SkillSrc | Out-Null; Ok "/reel -> $SkillDest (linked)" }
  catch { Copy-Item -Recurse $SkillSrc $SkillDest; Ok "/reel -> $SkillDest (copied; run install.ps1 -SkillOnly after updates)" }
}

if ($SkillOnly) { Install-Skill; exit 0 }

Say "Reel Room installer"
$free = [math]::Round((Get-PSDrive ($env:USERPROFILE.Substring(0,1))).Free / 1GB)
Write-Host "  free disk: $free GB (the install uses about 3.5 GB)"
if ($free -lt 10) { Write-Host "  WARNING: under 10 GB free. Renders need 2 to 5 GB each." -ForegroundColor Yellow }

Say "1/6 Python 3.11 to 3.13"
$Py = $null
foreach ($v in "3.12", "3.11", "3.13") {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    $p = & py "-$v" -c "import sys;print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $p) { $Py = $p.Trim(); break }
  }
}
if (-not $Py) { Winget-Install "Python.Python.3.12" "Python 3.12"; $Py = (& py -3.12 -c "import sys;print(sys.executable)").Trim() }
if (-not $Py) { Stop-Install "Python 3.12 not found after install. Open a new PowerShell and run install.ps1 again." }
Ok $Py

Say "2/6 ffmpeg and Node 22+"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Winget-Install "Gyan.FFmpeg" "ffmpeg" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Stop-Install "ffmpeg was installed but is not on PATH yet. Open a new PowerShell and run install.ps1 again." }
Ok "ffmpeg"
$nodeMajor = 0
if (Get-Command node -ErrorAction SilentlyContinue) { $nodeMajor = [int]((node -v) -replace "v(\d+).*", '$1') }
if ($nodeMajor -lt 22) { Winget-Install "OpenJS.NodeJS.LTS" "Node.js 22+" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Stop-Install "Node was installed but is not on PATH yet. Open a new PowerShell and run install.ps1 again." }
Ok ("node " + (node -v))

Say "3/6 Python environment ($Venv) with pinned packages"
New-Item -ItemType Directory -Force -Path $RRHome | Out-Null
if (-not (Test-Path $VenvPy)) { & $Py -m venv $Venv; if ($LASTEXITCODE) { Stop-Install "could not create the venv" } }
& $VenvPy -m pip install --disable-pip-version-check -q --upgrade pip
& $VenvPy -m pip install --disable-pip-version-check -r (Join-Path $Here "requirements.txt")
if ($LASTEXITCODE) { Stop-Install "pip install failed (check your internet, then run install.ps1 again)" }
Ok "packages installed"

Say "4/6 Models, GSAP and HyperFrames (one time; downloads resume if interrupted)"
$assetArgs = @("assets"); if ($NoModels) { $assetArgs += "--no-models" }
& $VenvPy (Join-Path $SkillSrc "tools\reel_cli.py") @assetArgs
if ($LASTEXITCODE) { Stop-Install "a download failed. Run install.ps1 again to resume." }

Say "5/6 Keys, brand and the /reel skill"
$envFile = Join-Path $Here ".env"
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $Here ".env.example") $envFile; Ok "created .env from .env.example (keys are optional, see the comments inside)" }
$homeEnv = Join-Path $RRHome ".env"
if (-not (Test-Path $homeEnv)) { Copy-Item $envFile $homeEnv; Ok "copied .env to $homeEnv (reel keeps it in sync)" }
@{ repo = $Here; installed = (Get-Date -Format s) } | ConvertTo-Json | Set-Content (Join-Path $RRHome "install.json")
if (-not (Test-Path (Join-Path $RRHome "brand.json"))) {
  & $VenvPy (Join-Path $SkillSrc "tools\reel_cli.py") setup --defaults | Out-Null
  Ok "default brand written (run .\reel.cmd setup to make it yours)"
}
Install-Skill

Say "6/6 Checking everything"
& $VenvPy (Join-Path $SkillSrc "tools\reel_cli.py") doctor
$rc = $LASTEXITCODE
$secs = [int]((Get-Date) - $T0).TotalSeconds
Say ("Install finished in {0} min {1} s" -f [math]::Floor($secs / 60), ($secs % 60))
if ($rc -eq 0) {
  Write-Host "  Next:  .\reel.cmd setup   (your name, handle, colours)"
  Write-Host "         .\reel.cmd demo    (renders the sample reel, a few minutes)"
  Write-Host "         then open Claude Code and type /reel"
} else { Write-Host "  Fix the FAIL lines above (each has its exact command), then run .\reel.cmd doctor" }
exit $rc
