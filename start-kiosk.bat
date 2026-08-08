@echo off
REM ===========================================================================
REM  LUNCH meal-access  --  START the kiosk (manual)
REM
REM  Starts the app, the proxy, the ngrok tunnel and opens the kiosk screen.
REM  This is the file the Desktop "LUNCH - Start" shortcut points at.
REM
REM  Normally you do not need it: the kiosk starts by itself when you log in.
REM  Use it after stop.bat, or if the screen is ever not running.
REM
REM  Safe to run twice - it stops the old processes before starting new ones.
REM
REM  Keep ALL text ASCII.
REM ===========================================================================

setlocal
cd /d "%~dp0"

echo.
echo === Starting LUNCH ===
echo.
echo Please wait - this takes about 10-20 seconds.
echo The kiosk screen opens by itself when it is ready.
echo.

call quick-start.bat

REM quick-start exits on its own once the kiosk page is open; it already
REM waits for the app to answer before opening the browser, so there is
REM nothing to verify here.
endlocal
