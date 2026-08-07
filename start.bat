@echo off
REM ===========================================================================
REM  LUNCH meal-access  --  one-click start for Windows
REM
REM  First run (needs internet ONCE):
REM    * creates a Python virtual environment in .venv
REM    * installs dependencies from requirements.txt
REM    * generates SECRET_KEY and TUNNEL_SECRET into .env if missing
REM    * downloads ngrok.exe
REM    * seeds the database (admin + sample cards) if the DB is missing
REM
REM  Every run:
REM    * starts the app (bound to 127.0.0.1 -- NOT reachable from the LAN)
REM    * starts the local header-injecting proxy (adds the tunnel secret)
REM    * opens the local kiosk screen
REM    * starts the ngrok tunnel hidden in the background
REM    * prints the stable ngrok URL for remote admin
REM
REM  After first setup the SCAN screen works fully OFFLINE forever. The tunnel
REM  only matters when you want to reach Admin / Reports remotely.
REM
REM  Keep ALL text in this file ASCII. The app text is Georgian (in Python/HTML).
REM ===========================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM On the FIRST pass, re-launch this script in a child cmd whose entire output
REM is copied to start-log.txt, then ALWAYS pause. This guarantees a transcript
REM and a visible window even if the work aborts (parse error, crash, etc.).
if not "%~1"=="__inner" (
  echo Starting LUNCH... a full log is being written to start-log.txt
  cmd /v:on /c ""%~f0" __inner" > "start-log.txt" 2>&1
  set "RC=!errorlevel!"
  echo.
  type "start-log.txt"
  echo.
  echo ===========================================================================
  if not "!RC!"=="0" echo [start.bat] finished with code !RC!. See start-log.txt above.
  echo Press any key to close this window . . .
  pause >nul
  exit /b !RC!
)

setlocal EnableDelayedExpansion

echo.
echo === LUNCH meal-access : startup ===
echo.

REM ---------------------------------------------------------------------------
REM  1. Find a Python launcher
REM ---------------------------------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python was not found on PATH.
  echo         Install Python 3.11+ from https://www.python.org/downloads/
  echo         and CHECK "Add Python to PATH" during install, then re-run this file.
  exit /b 1
)
echo Using Python launcher: %PY%

REM ---------------------------------------------------------------------------
REM  2. Create / reuse the virtual environment
REM ---------------------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment in .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create the virtual environment.
    exit /b 1
  )
)
set "VENV_PY=.venv\Scripts\python.exe"

REM ---------------------------------------------------------------------------
REM  3. Install / update dependencies
REM ---------------------------------------------------------------------------
echo Installing dependencies ^(first run needs internet^) ...

REM Some Windows Python installs create a venv without pip. Bootstrap it.
"%VENV_PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo pip is missing in .venv; trying ensurepip ...
  "%VENV_PY%" -m ensurepip --upgrade
)
"%VENV_PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo ensurepip did not work; downloading get-pip.py ...
  "%VENV_PY%" -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py','get-pip.py')"
  if errorlevel 1 (
    echo [ERROR] Could not download get-pip.py. Check internet and try again.
    exit /b 1
  )
  "%VENV_PY%" get-pip.py
  if errorlevel 1 (
    echo [ERROR] Could not install pip. Install the full Python 3.11 installer with pip enabled.
    exit /b 1
  )
  del /q get-pip.py >nul 2>&1
)

"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed. Check your internet connection and try again.
  exit /b 1
)

REM ---------------------------------------------------------------------------
REM  4. Ensure .env exists and has SECRET_KEY + TUNNEL_SECRET
REM ---------------------------------------------------------------------------
if not exist ".env" (
  echo Creating .env from .env.example ...
  copy /y ".env.example" ".env" >nul
  echo.
  echo [ACTION REQUIRED] Open .env and set a STRONG ADMIN_PASSWORD, then re-run.
  echo                   SECRET_KEY and TUNNEL_SECRET will be auto-filled now.
)

REM Auto-fill SECRET_KEY and TUNNEL_SECRET if blank. This helper also prints
REM nothing on success; it edits .env in place.
"%VENV_PY%" scripts\ensure_secrets.py
if errorlevel 1 (
  echo [ERROR] Could not prepare secrets in .env
  exit /b 1
)

REM ---------------------------------------------------------------------------
REM  5. Validate config (refuses weak password / missing SECRET_KEY) + seed DB
REM ---------------------------------------------------------------------------
"%VENV_PY%" scripts\startup_prepare.py
if errorlevel 1 (
  echo.
  echo [ERROR] Startup checks failed ^(see message above^).
  echo         Most likely: set a strong ADMIN_PASSWORD in .env, then re-run.
  exit /b 1
)

REM ---------------------------------------------------------------------------
REM  6. Download ngrok.exe once
REM ---------------------------------------------------------------------------
if not exist "ngrok.exe" (
  echo Downloading ngrok.exe ...
  "%VENV_PY%" scripts\download_ngrok.py
  if errorlevel 1 (
    echo [WARN] Could not download ngrok.exe. The app + scan screen will
    echo        still run locally; remote admin via tunnel will be unavailable
    echo        until ngrok.exe is present. See the manual download note above.
  )
)

REM ---------------------------------------------------------------------------
REM  7. Read PORT / PROXY_PORT / ngrok settings from .env
REM ---------------------------------------------------------------------------
REM Parse .env in Python (batch is fragile with special chars in secrets and
REM would otherwise abort the whole script silently). read_env.py prints clean
REM `set "KEY=VALUE"` lines for PORT, PROXY_PORT, NGROK_AUTHTOKEN, NGROK_DOMAIN.
set "PORT=8000"
set "PROXY_PORT=8001"
set "NGROK_AUTHTOKEN="
set "NGROK_DOMAIN="
for /f "usebackq delims=" %%i in (`"%VENV_PY%" scripts\read_env.py`) do %%i

REM ---------------------------------------------------------------------------
REM  8. Start the app (hidden) and the header-injecting proxy (hidden)
REM ---------------------------------------------------------------------------
echo.
if exist "lunch-pids.txt" (
  echo Stopping previous LUNCH background processes ...
  for /f "tokens=1,2,*" %%a in (lunch-pids.txt) do (
    taskkill /PID %%b /T /F >nul 2>&1
  )
  del /q "lunch-pids.txt" >nul 2>&1
)
if exist "app.log" del /q "app.log"
if exist "proxy.log" del /q "proxy.log"

echo Starting the app on http://127.0.0.1:%PORT% ...
"%VENV_PY%" scripts\start_hidden.py --label app --log app.log --pid-file lunch-pids.txt -- "%VENV_PY%" run.py
if errorlevel 1 (
  echo [ERROR] Could not start the app. Check app.log.
  exit /b 1
)
"%VENV_PY%" scripts\wait_for_http.py "http://127.0.0.1:%PORT%/healthz" --label app --seconds 25
if errorlevel 1 (
  echo.
  echo [ERROR] App did not start correctly. app.log follows:
  echo ---------------------------------------------------------------------------
  if exist "app.log" type "app.log"
  echo ---------------------------------------------------------------------------
  echo Try double-clicking stop.bat, then run start.bat again.
  exit /b 1
)

echo Starting the tunnel proxy on http://127.0.0.1:%PROXY_PORT% ...
set "PROXY_PORT=%PROXY_PORT%"
"%VENV_PY%" scripts\start_hidden.py --label proxy --env PROXY_PORT=%PROXY_PORT% --log proxy.log --pid-file lunch-pids.txt -- "%VENV_PY%" tunnel_proxy.py
if errorlevel 1 (
  echo [ERROR] Could not start the tunnel proxy. Check proxy.log.
  exit /b 1
)
"%VENV_PY%" scripts\wait_for_http.py "http://127.0.0.1:%PROXY_PORT%/healthz" --label proxy --seconds 15
if errorlevel 1 (
  echo.
  echo [ERROR] Tunnel proxy did not start correctly. proxy.log follows:
  echo ---------------------------------------------------------------------------
  if exist "proxy.log" type "proxy.log"
  echo ---------------------------------------------------------------------------
  echo Try double-clicking stop.bat, then run start.bat again.
  exit /b 1
)

REM ---------------------------------------------------------------------------
REM  9. Open the kiosk screen locally.
REM ---------------------------------------------------------------------------
echo Opening kiosk screen ...
start "" "http://127.0.0.1:%PORT%/"

REM ---------------------------------------------------------------------------
REM  10. Start ngrok hidden, pointed at the PROXY port.
REM      The stable public URL is saved into tunnel-url.txt and printed.
REM ---------------------------------------------------------------------------
REM Flattened with goto + delayed expansion (!VAR!) so an empty/odd value can
REM never mis-parse a nested parenthesized block and abort the script.
if not exist "ngrok.exe" (
  echo [INFO] Skipping tunnel ^(ngrok.exe missing^).
  goto :after_tunnel
)
if exist "tunnel-url.txt" del /q "tunnel-url.txt"
if exist "tunnel.log" del /q "tunnel.log"
if "!NGROK_AUTHTOKEN!"=="" (
  echo [INFO] NGROK_AUTHTOKEN is empty in .env. Skipping remote admin tunnel.
  goto :after_tunnel
)
if "!NGROK_DOMAIN!"=="" (
  echo [INFO] NGROK_DOMAIN is empty in .env. Skipping remote admin tunnel.
  goto :after_tunnel
)
echo Configuring ngrok auth token ...
".\ngrok.exe" config add-authtoken "!NGROK_AUTHTOKEN!" >nul
if errorlevel 1 (
  echo [WARN] Could not configure ngrok authtoken. Check NGROK_AUTHTOKEN in .env.
  goto :after_tunnel
)
echo Starting ngrok tunnel at https://!NGROK_DOMAIN! ...
"%VENV_PY%" scripts\start_hidden.py --label tunnel --log tunnel.log --pid-file lunch-pids.txt -- ".\ngrok.exe" http --url !NGROK_DOMAIN! http://127.0.0.1:!PROXY_PORT!
"%VENV_PY%" scripts\print_remote_url.py
:after_tunnel

echo.
echo ===========================================================================
echo  KIOSK ^(local, offline^):   http://127.0.0.1:%PORT%/
echo  The kiosk page was opened automatically. Press F11 in the browser.
echo.
echo  REMOTE ADMIN URL is shown above and saved in tunnel-url.txt.
echo  Open /admin or /reports on it from your own laptop/phone.
echo  Admin/Reports are BLOCKED on the local machine by design.
echo  To stop the background processes, double-click stop.bat.
echo ===========================================================================
echo.
echo This window can stay open, or you can close it after copying the URLs.
endlocal
