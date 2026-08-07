@echo off
REM ===========================================================================
REM  LUNCH meal-access  --  REMOVE AUTOSTART + WATCHDOG
REM
REM  Undoes install-autostart.bat: the kiosk no longer starts on logon and is
REM  no longer revived automatically. The app, database, and settings are NOT
REM  touched - only the two Windows Scheduled Tasks are removed.
REM
REM  After this you start the kiosk manually with start.bat or quick-start.bat.
REM
REM  Keep ALL text ASCII.
REM ===========================================================================

setlocal
echo.
echo === Removing LUNCH autostart + watchdog ===
echo.

schtasks /Delete /TN "LunchKioskStartup" /F >nul 2>&1
if errorlevel 1 (
  echo   [--] LunchKioskStartup was not installed.
) else (
  echo   [OK] LunchKioskStartup removed.
)

schtasks /Delete /TN "LunchKioskWatchdog" /F >nul 2>&1
if errorlevel 1 (
  echo   [--] LunchKioskWatchdog was not installed.
) else (
  echo   [OK] LunchKioskWatchdog removed.
)

echo.
echo Done. Your data and settings were not touched.
echo Start the kiosk manually with start.bat when you need it.
echo.
pause
endlocal
