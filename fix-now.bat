@echo off
REM ===========================================================================
REM  LUNCH meal-access  --  FIX NOW  (run this when the kiosk is down)
REM
REM  Diagnoses and repairs the "502 upstream error" case: tunnel is alive but
REM  the app behind it is not running. Prints exactly what it finds, so if it
REM  cannot fix it you have something concrete to report.
REM
REM  Safe to run at any time. Never touches lunch.db, .env, or backups.
REM
REM  Keep ALL text ASCII.
REM ===========================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ================= LUNCH: diagnose ^& fix =================
echo.

set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [FATAL] .venv is missing. The app cannot run at all.
  echo         Fix: run start.bat, which rebuilds it.
  echo.
  pause
  exit /b 1
)
echo [ok] .venv found

REM --- 1) can the app's code even be imported? ------------------------------
echo.
echo --- Checking the app can start ---
"%VENV_PY%" -c "import sys; sys.path.insert(0,'.'); import app.main; print('[ok] app code imports cleanly')" 2>app-import-error.txt
if errorlevel 1 (
  echo [FATAL] The app code FAILS to import. This is why it will not start:
  echo.
  type app-import-error.txt
  echo.
  echo         A previous version is stored in .rollback\ - restoring it:
  if exist ".rollback\app" (
    xcopy /E /I /Y ".rollback\app" "app" >nul 2>&1
    xcopy /E /I /Y ".rollback\scripts" "scripts" >nul 2>&1
    xcopy /E /I /Y ".rollback\static" "static" >nul 2>&1
    echo         [ok] rollback restored - continuing.
  ) else (
    echo         [!!] no .rollback snapshot available.
    pause
    exit /b 1
  )
) else (
  del /q app-import-error.txt >nul 2>&1
)

REM --- 2) show the tail of the app log --------------------------------------
if exist "app.log" (
  echo.
  echo --- Last lines of app.log ---
  powershell -NoProfile -Command "Get-Content app.log -Tail 15" 2>nul
)

REM --- 3) are the scheduled tasks actually registered? ----------------------
echo.
echo --- Scheduled tasks ---
schtasks /Query /TN "LunchKioskStartup" >nul 2>&1
if errorlevel 1 (echo [!!] LunchKioskStartup  NOT registered) else (echo [ok] LunchKioskStartup registered)
schtasks /Query /TN "LunchKioskWatchdog" >nul 2>&1
if errorlevel 1 (
  echo [!!] LunchKioskWatchdog NOT registered - this is why it did not self-heal.
  echo      Fix: run install-autostart.bat as administrator.
) else (
  echo [ok] LunchKioskWatchdog registered
)

REM --- 4) clean slate: kill everything, including stray ngrok ---------------
echo.
echo --- Stopping any leftovers ---
if exist "lunch-pids.txt" (
  for /f "tokens=1,2,*" %%a in (lunch-pids.txt) do taskkill /PID %%b /T /F >nul 2>&1
  del /q "lunch-pids.txt" >nul 2>&1
)
taskkill /IM ngrok.exe /T /F >nul 2>&1
echo [ok] stopped old app / proxy / tunnel processes
"%VENV_PY%" -c "import time;time.sleep(2)" >nul 2>&1

REM --- 5) start everything fresh -------------------------------------------
echo.
echo --- Starting the kiosk ---
call quick-start.bat /noupdate

REM --- 6) verify it actually came up ----------------------------------------
echo.
echo --- Verifying ---
set "PORT=8000"
for /f "usebackq delims=" %%i in (`"%VENV_PY%" scripts\read_env.py`) do %%i
"%VENV_PY%" scripts\wait_for_http.py "http://127.0.0.1:!PORT!/healthz" --seconds 45 --label app
if errorlevel 1 (
  echo.
  echo [FAIL] The app still is not answering. Send these lines for diagnosis:
  if exist "app.log" powershell -NoProfile -Command "Get-Content app.log -Tail 20" 2>nul
) else (
  echo.
  echo [SUCCESS] The kiosk is running again.
  echo           Reload your ngrok link - it should work now.
)

echo.
pause
endlocal
