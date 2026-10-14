@echo off
rem Reel Room command line. Run: reel.cmd help
setlocal
if "%REEL_ROOM_HOME%"=="" set "REEL_ROOM_HOME=%USERPROFILE%\.reel-room"
set "PY=%REEL_ROOM_HOME%\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"
%PY% "%~dp0skills\reel\tools\reel_cli.py" %*
