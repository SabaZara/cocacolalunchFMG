@echo off
REM Create diagnose.txt with startup/environment details.
REM Keep this file ASCII-only.

setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "OUT=diagnose.txt"
echo LUNCH diagnose > "%OUT%"
echo Generated: %DATE% %TIME% >> "%OUT%"
echo Folder: %CD% >> "%OUT%"
echo. >> "%OUT%"

echo === Files === >> "%OUT%"
dir /b >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === Python discovery === >> "%OUT%"
where py >> "%OUT%" 2>&1
where python >> "%OUT%" 2>&1
py -3 --version >> "%OUT%" 2>&1
python --version >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === .env exists === >> "%OUT%"
if exist ".env" (
  echo YES >> "%OUT%"
) else (
  echo NO >> "%OUT%"
)
echo. >> "%OUT%"

echo === Existing venv === >> "%OUT%"
if exist ".venv\Scripts\python.exe" (
  echo YES >> "%OUT%"
  ".venv\Scripts\python.exe" --version >> "%OUT%" 2>&1
  ".venv\Scripts\python.exe" -m pip --version >> "%OUT%" 2>&1
) else (
  echo NO >> "%OUT%"
)
echo. >> "%OUT%"

echo === Port check 8000/8001 === >> "%OUT%"
netstat -ano | findstr ":8000" >> "%OUT%" 2>&1
netstat -ano | findstr ":8001" >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === pip install (captures wheel/build failures) === >> "%OUT%"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%OUT%" 2>&1
  echo pip exit code: !errorlevel! >> "%OUT%"
) else (
  echo Cannot run pip: .venv missing >> "%OUT%"
)
echo. >> "%OUT%"

echo === Startup prepare === >> "%OUT%"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\startup_prepare.py >> "%OUT%" 2>&1
  echo startup_prepare exit code: !errorlevel! >> "%OUT%"
) else (
  echo Cannot run startup_prepare: .venv missing >> "%OUT%"
)
echo. >> "%OUT%"

echo === Hidden-launch test (does start_hidden actually spawn the app?) === >> "%OUT%"
if exist ".venv\Scripts\python.exe" (
  if exist "diag-app.log" del /q "diag-app.log"
  ".venv\Scripts\python.exe" scripts\start_hidden.py --label diag --log diag-app.log --pid-file diag-pids.txt -- ".venv\Scripts\python.exe" run.py >> "%OUT%" 2>&1
  echo start_hidden exit code: !errorlevel! >> "%OUT%"
  ".venv\Scripts\python.exe" scripts\wait_for_http.py "http://127.0.0.1:8000/healthz" --label diag --seconds 15 >> "%OUT%" 2>&1
  echo --- diag-app.log --- >> "%OUT%"
  if exist "diag-app.log" type "diag-app.log" >> "%OUT%" 2>&1
  echo --- end diag-app.log --- >> "%OUT%"
  REM stop the diagnostic app instance
  if exist "diag-pids.txt" (
    for /f "tokens=1,2,*" %%a in (diag-pids.txt) do taskkill /PID %%b /T /F >nul 2>&1
    del /q "diag-pids.txt" >nul 2>&1
  )
) else (
  echo Cannot test hidden launch: .venv missing >> "%OUT%"
)
echo. >> "%OUT%"

echo === Direct app import check === >> "%OUT%"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "from app.main import app; print('import ok')" >> "%OUT%" 2>&1
) else (
  echo Cannot import app: .venv missing >> "%OUT%"
)
echo. >> "%OUT%"

echo Diagnose written to %OUT%
echo Please send diagnose.txt
pause
endlocal
