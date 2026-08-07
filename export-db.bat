@echo off
REM ===========================================================================
REM  LUNCH  --  export the database as ONE safe file
REM
REM  Run this in the OLD folder BEFORE installing a new version.
REM
REM  SQLite keeps recent changes in lunch.db-wal, so copying lunch.db alone can
REM  LOSE DATA. This makes a single consolidated file:  lunch-export.db
REM  which already contains everything. Copy that one file to the new folder
REM  and rename it to lunch.db.
REM
REM  Keep this file ASCII-only.
REM ===========================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo === LUNCH : export database ===
echo.

set "VENV_PY=.venv\Scripts\python.exe"
set "PY="
if exist "%VENV_PY%" set "PY=%VENV_PY%"
if not defined PY ( where py >nul 2>&1 && set "PY=py -3" )
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo [ERROR] Python not found. Cannot export.
  pause
  exit /b 1
)

%PY% scripts\export_db.py
if errorlevel 1 (
  echo.
  echo [ERROR] Export failed. See the message above.
  pause
  exit /b 1
)

echo.
echo Copy  lunch-export.db  into the NEW folder and rename it to  lunch.db
echo.
pause
endlocal
