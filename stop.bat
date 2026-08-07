@echo off
REM Stop LUNCH background processes started by start.bat.
REM Keep this file ASCII-only.

setlocal
cd /d "%~dp0"

if not exist "lunch-pids.txt" (
  echo No lunch-pids.txt found. Nothing to stop.
  pause
  exit /b 0
)

echo Stopping LUNCH background processes...
for /f "tokens=1,2,*" %%a in (lunch-pids.txt) do (
  echo Stopping %%a (PID %%b)...
  taskkill /PID %%b /T /F >nul 2>&1
)

del /q "lunch-pids.txt" >nul 2>&1
echo Done.
pause
endlocal
