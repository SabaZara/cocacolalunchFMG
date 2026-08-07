@echo off
REM Open the local kiosk reader simulator. Run start.bat first if the app is not up.
REM Keep this file ASCII-only.

setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM Read only the PORT line from .env via findstr (robust: secret-laden lines
REM with special characters can never reach or abort the parser). Default 8000.
set "PORT=8000"
if exist ".env" (
  for /f "usebackq tokens=2 delims==" %%a in (`findstr /b /i "PORT=" ".env"`) do set "PORT=%%a"
)
set "PORT=!PORT: =!"

start "" "http://127.0.0.1:!PORT!/kiosk-test"
endlocal
