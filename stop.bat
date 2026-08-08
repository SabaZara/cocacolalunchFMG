@echo off
REM ===========================================================================
REM  LUNCH meal-access  --  STOP everything
REM
REM  Stops the app, the proxy and the ngrok tunnel. The kiosk screen stops
REM  working until you start it again, so use this when you are done for the
REM  day (or before doing maintenance on the laptop).
REM
REM  NOTE: this does NOT disable the automatic start. Turning the laptop on
REM  again (or the 5-minute watchdog) will bring the kiosk back. To stop it
REM  starting by itself, run uninstall-autostart.bat.
REM
REM  Nothing is deleted: lunch.db, .env, backups/ and settings are untouched.
REM
REM  Keep ALL text ASCII.
REM ===========================================================================

setlocal
cd /d "%~dp0"

echo.
echo === Stopping LUNCH ===
echo.

REM 1) the processes we recorded
if exist "lunch-pids.txt" (
  for /f "tokens=1,2,*" %%a in (lunch-pids.txt) do (
    echo   stopping %%a ^(PID %%b^)
    taskkill /PID %%b /T /F >nul 2>&1
  )
  del /q "lunch-pids.txt" >nul 2>&1
) else (
  echo   no pid file - sweeping by name instead
)

REM 2) ...and anything the pid file missed. A hard power-off or a crash
REM    leaves a stale/absent pid file behind, and a surviving ngrok agent
REM    then blocks the next one (free plan allows exactly ONE agent), so
REM    remote access would break on the next start.
taskkill /IM ngrok.exe /T /F >nul 2>&1
echo   cleared any leftover ngrok tunnel

echo.
echo Stopped. The kiosk screen will not work until you start it again.
echo Start it with:  start-kiosk.bat  (or start.bat)
echo.
pause
endlocal
