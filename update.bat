@echo off
REM ===========================================================================
REM  LUNCH meal-access  --  UPDATE from GitHub (no git needed)
REM
REM  Downloads the latest code ZIP from your PUBLIC GitHub repo, copies the code
REM  over this install (PRESERVING .env, lunch.db, backups/, ngrok.exe), then
REM  restarts the app + proxy + tunnel.
REM
REM  >>> SET YOUR REPO ON THE NEXT LINE (format: owner/repo) <<<
REM      example:  set "GITHUB_REPO=SabaZara/cocacolalunchFMG"
REM ===========================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "GITHUB_REPO=SabaZara/cocacolalunchFMG"
set "GITHUB_BRANCH=main"

set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERROR] .venv not found. Run start.bat once first.
  pause
  exit /b 1
)

echo.
echo === LUNCH update from github.com/%GITHUB_REPO% ^(%GITHUB_BRANCH%^) ===
echo.

REM 1) download + apply the latest code (preserves data + secrets)
"%VENV_PY%" scripts\apply_update.py
if errorlevel 1 (
  echo.
  echo [ERROR] Update failed. Nothing was restarted. See the message above.
  pause
  exit /b 1
)

REM 2) (re)install deps in case requirements.txt changed (safe if unchanged)
echo Updating dependencies if needed ...
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [WARN] pip install reported a problem; continuing to restart anyway.
)

REM 3) restart the app + proxy + tunnel using the existing quick-start flow
echo.
echo Restarting LUNCH ...
if exist "quick-start.bat" (
  call "quick-start.bat"
) else (
  echo [WARN] quick-start.bat missing; run start.bat to relaunch.
)

echo.
echo Update complete. If you only changed admin/reports pages, just HARD-REFRESH
echo your browser (Ctrl+F5) to see them.
pause
endlocal
