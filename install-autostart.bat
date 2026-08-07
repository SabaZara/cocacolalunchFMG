@echo off
REM ===========================================================================
REM  LUNCH meal-access  --  INSTALL AUTOSTART + WATCHDOG  (run ONCE)
REM
REM  Registers two Windows Scheduled Tasks so the kiosk runs itself:
REM
REM    1. LunchKioskStartup  -- at every logon, launch app + proxy + tunnel and
REM                             open the kiosk screen. Turn the laptop on and it
REM                             is ready to scan; nothing to click.
REM    2. LunchKioskWatchdog -- every 5 minutes, check the app answers /healthz
REM                             and relaunch it if it does not. A failed remote
REM                             update or a crash can no longer strand the kiosk
REM                             and force a walk to the PC.
REM
REM  Shutdown stays fully manual: nothing here ever closes or stops anything.
REM  You shut the laptop down when your day ends, exactly as before.
REM
REM  Safe to re-run (tasks are replaced, not duplicated).
REM  To remove them later, run uninstall-autostart.bat.
REM
REM  Keep ALL text ASCII.
REM ===========================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PROJ=%~dp0"
if "%PROJ:~-1%"=="\" set "PROJ=%PROJ:~0,-1%"

set "VENV_PY=%PROJ%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERROR] .venv not found. Run start.bat once first, then re-run this.
  pause
  exit /b 1
)

echo.
echo === Installing LUNCH autostart + watchdog ===
echo Project: %PROJ%
echo.

REM --- 1) start at logon ----------------------------------------------------
REM Runs quick-start.bat minimized. /RL HIGHEST avoids the UAC prompt at logon.
schtasks /Create /TN "LunchKioskStartup" /SC ONLOGON /RL HIGHEST /F ^
  /TR "cmd /c cd /d \"%PROJ%\" && start \"\" /min quick-start.bat" >nul 2>&1
if errorlevel 1 (
  echo [WARN] Could not create the logon task with HIGHEST. Retrying normally...
  schtasks /Create /TN "LunchKioskStartup" /SC ONLOGON /F ^
    /TR "cmd /c cd /d \"%PROJ%\" && start \"\" /min quick-start.bat" >nul 2>&1
)
if errorlevel 1 (
  echo [ERROR] Failed to register the logon task.
  echo         Right-click this file and pick "Run as administrator".
  pause
  exit /b 1
)
echo   [OK] LunchKioskStartup   -- starts everything when you log in

REM --- 2) watchdog every 5 minutes -----------------------------------------
schtasks /Create /TN "LunchKioskWatchdog" /SC MINUTE /MO 5 /RL HIGHEST /F ^
  /TR "\"%VENV_PY%\" \"%PROJ%\scripts\watchdog.py\"" >nul 2>&1
if errorlevel 1 (
  schtasks /Create /TN "LunchKioskWatchdog" /SC MINUTE /MO 5 /F ^
    /TR "\"%VENV_PY%\" \"%PROJ%\scripts\watchdog.py\"" >nul 2>&1
)
if errorlevel 1 (
  echo [WARN] Failed to register the watchdog task. Autostart still works.
) else (
  echo   [OK] LunchKioskWatchdog  -- revives the app if it ever stops
)

echo.
echo Done. Testing the watchdog once now...
"%VENV_PY%" "%PROJ%\scripts\watchdog.py" --verbose
echo.
echo ===========================================================================
echo  Setup complete.
echo.
echo  From now on: turn the laptop on, log in, and the kiosk starts by itself.
echo  Shut down normally when your day ends - nothing here interferes with that.
echo ===========================================================================
echo.
pause
endlocal
