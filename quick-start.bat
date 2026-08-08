@echo off
REM ===========================================================================
REM  LUNCH meal-access  --  QUICK START (minimal, auto-closing)
REM
REM  Just (re)launches the app + proxy + tunnel in the background, then closes.
REM  No setup, no install, no health-wait, no pause. Use AFTER start.bat has
REM  done the first-time setup.
REM
REM  This file may live INSIDE the project, or on the Desktop. It finds the
REM  project automatically:
REM    1. the folder this .bat is in (if it contains run.py), else
REM    2. the known Downloads location, else
REM    3. it briefly shows an error and exits.
REM  If your project is elsewhere, set PROJ below to its full path.
REM
REM  Keep ALL text ASCII.
REM ===========================================================================

setlocal EnableDelayedExpansion

REM --- locate the project folder -------------------------------------------
set "PROJ="
if exist "%~dp0run.py" set "PROJ=%~dp0"
if not defined PROJ if exist "%USERPROFILE%\Downloads\lunchFMG-kiosk-ready-private\lunchFMG-kiosk-ready\run.py" set "PROJ=%USERPROFILE%\Downloads\lunchFMG-kiosk-ready-private\lunchFMG-kiosk-ready\"

if not defined PROJ (
  echo [ERROR] Could not find the LUNCH project folder.
  echo Put quick-start.bat inside the project, or edit PROJ in this file.
  timeout /t 6 >nul
  exit /b 1
)

cd /d "%PROJ%"
set "VENV_PY=.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo [ERROR] .venv not found in "%PROJ%". Run start.bat once first.
  timeout /t 6 >nul
  exit /b 1
)

REM --- read PORT / PROXY_PORT / ngrok settings from .env --------------------
set "PORT=8000"
set "PROXY_PORT=8001"
set "NGROK_AUTHTOKEN="
set "NGROK_DOMAIN="
set "GITHUB_REPO=SabaZara/cocacolalunchFMG"
set "GITHUB_BRANCH=main"
for /f "usebackq delims=" %%i in (`"%VENV_PY%" scripts\read_env.py`) do %%i

REM --- flags ---------------------------------------------------------------
REM   /nobrowser  do not open the kiosk tab (used by the watchdog, which only
REM               revives a dead app - it must never spawn extra tabs).
REM   /noupdate   skip the GitHub pull (faster start; the watchdog uses this
REM               so a revive is immediate instead of waiting on a download).
set "OPEN_BROWSER=1"
set "DO_UPDATE=1"
for %%a in (%*) do (
  if /I "%%~a"=="/nobrowser" set "OPEN_BROWSER=0"
  if /I "%%~a"=="/noupdate"  set "DO_UPDATE=0"
)

REM --- pull latest code from GitHub before launch (best-effort) ------------
REM So a reboot + quick-start also APPLIES updates. Offline-safe: if the pull
REM fails (no internet), apply_update leaves the current code untouched and we
REM launch anyway, so scanning always works. Data (.env, lunch.db) preserved.
if "!DO_UPDATE!"=="1" (
  "%VENV_PY%" scripts\apply_update.py
)

REM --- stop any previous LUNCH background processes -------------------------
REM First the PIDs we recorded...
if exist "lunch-pids.txt" (
  for /f "tokens=1,2,*" %%a in (lunch-pids.txt) do (
    taskkill /PID %%b /T /F >nul 2>&1
  )
  del /q "lunch-pids.txt" >nul 2>&1
)

REM --- clear the browser's HTTP cache (only when it is NOT running) --------
REM The page is served no-store, but the on-disk cache still grows for months
REM and a full disk stops SQLite writing (i.e. scans fail at the reader). A
REM corrupted cache has also broken the scan page here before. Skipped
REM automatically if a browser is open, so no profile can be damaged.
if "!OPEN_BROWSER!"=="1" (
  "%VENV_PY%" scripts\clear_browser_cache.py >nul 2>&1
)

REM ...then ANY ngrok still running, whether we recorded it or not.
REM The free ngrok plan allows exactly ONE agent: if a stale one survives
REM (hard power-off, crash, deleted pid file, recycled PID) the new one dies
REM with ERR_NGROK_108 and remote access is lost completely. The pid file
REM alone cannot be trusted, so kill by image name as well.
taskkill /IM ngrok.exe /T /F >nul 2>&1

REM Give the old agent a moment to drop its session server-side, otherwise
REM the replacement can still be refused as a duplicate.
"%VENV_PY%" -c "import time;time.sleep(2)" >nul 2>&1

REM --- launch app + proxy (detached, hidden) -------------------------------
"%VENV_PY%" scripts\start_hidden.py --label app --log app.log --pid-file lunch-pids.txt -- "%VENV_PY%" run.py
"%VENV_PY%" scripts\start_hidden.py --label proxy --env PROXY_PORT=!PROXY_PORT! --log proxy.log --pid-file lunch-pids.txt -- "%VENV_PY%" tunnel_proxy.py

REM --- launch tunnel if configured (detached, hidden) ----------------------
REM Exactly one agent: everything above was killed first, and the free ngrok
REM plan refuses a second one (ERR_NGROK_108) which would kill remote access.
if exist "ngrok.exe" if not "!NGROK_AUTHTOKEN!"=="" if not "!NGROK_DOMAIN!"=="" (
  ".\ngrok.exe" config add-authtoken "!NGROK_AUTHTOKEN!" >nul 2>&1
  "%VENV_PY%" scripts\start_hidden.py --label tunnel --log tunnel.log --pid-file lunch-pids.txt -- ".\ngrok.exe" http --url !NGROK_DOMAIN! http://127.0.0.1:!PROXY_PORT!
)

REM --- wait until the app actually answers, then open the kiosk ------------
REM Waiting on /healthz instead of a blind sleep: the page used to be opened
REM after a fixed 3s, so on a cold boot the browser hit a not-yet-listening
REM app and showed an error until someone reloaded it.
if "!OPEN_BROWSER!"=="1" (
  "%VENV_PY%" scripts\wait_for_http.py "http://127.0.0.1:!PORT!/healthz" --seconds 60 --label kiosk >nul 2>&1
  REM Cache-buster: a unique ?t= each launch, so the browser can NEVER serve a
  REM stale/corrupted cached copy of the scan page. (The app also sends
  REM Cache-Control: no-store, but this protects even a poisoned existing cache.)
  set "CB=!RANDOM!!RANDOM!"
  start "" "http://127.0.0.1:!PORT!/?t=!CB!"
)
endlocal
exit
