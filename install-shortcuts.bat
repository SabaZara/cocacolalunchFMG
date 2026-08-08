@echo off
REM ===========================================================================
REM  LUNCH meal-access  --  CREATE DESKTOP SHORTCUTS  (run ONCE)
REM
REM  Puts three shortcuts on the Desktop:
REM
REM    LUNCH - Start    starts the app + tunnel and opens the kiosk screen
REM    LUNCH - Stop     stops everything (kiosk screen stops working)
REM    LUNCH - Fix      diagnoses and repairs a kiosk that will not start
REM
REM  Safe to re-run: existing shortcuts are replaced.
REM  Deleting a shortcut removes only the shortcut, never the program.
REM
REM  Keep ALL text ASCII.
REM ===========================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PROJ=%~dp0"
if "%PROJ:~-1%"=="\" set "PROJ=%PROJ:~0,-1%"

REM Resolve the real Desktop path from the registry: OneDrive-backed and
REM localised Windows installs do NOT have it at %USERPROFILE%\Desktop.
set "DESKTOP="
for /f "usebackq tokens=2,*" %%a in (`reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop 2^>nul`) do set "DESKTOP=%%b"
if defined DESKTOP call set "DESKTOP=%DESKTOP%"
if not defined DESKTOP set "DESKTOP=%USERPROFILE%\Desktop"
if not exist "!DESKTOP!" set "DESKTOP=%USERPROFILE%\Desktop"

echo.
echo === Creating LUNCH desktop shortcuts ===
echo Project : %PROJ%
echo Desktop : !DESKTOP!
echo.

REM Build the shortcuts with PowerShell (WScript.Shell creates real .lnk
REM files, so they get a proper icon and a working "start in" folder).
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$proj = '%PROJ%'; $desk = '!DESKTOP!';" ^
  "$defs = @(" ^
  "  @{ Name='LUNCH - Start'; Target='start-kiosk.bat'; Desc='Start the LUNCH kiosk (app + tunnel + screen)'; Icon='imageres.dll,101' }," ^
  "  @{ Name='LUNCH - Stop';  Target='stop.bat';        Desc='Stop the LUNCH kiosk'; Icon='imageres.dll,100' }," ^
  "  @{ Name='LUNCH - Fix';   Target='fix-now.bat';     Desc='Diagnose and repair the LUNCH kiosk'; Icon='imageres.dll,81' }" ^
  ");" ^
  "foreach ($d in $defs) {" ^
  "  $tp = Join-Path $proj $d.Target;" ^
  "  if (-not (Test-Path $tp)) { Write-Host ('  [skip] ' + $d.Name + ' - ' + $d.Target + ' not found'); continue }" ^
  "  $lnk = $ws.CreateShortcut((Join-Path $desk ($d.Name + '.lnk')));" ^
  "  $lnk.TargetPath = $tp;" ^
  "  $lnk.WorkingDirectory = $proj;" ^
  "  $lnk.Description = $d.Desc;" ^
  "  $lnk.IconLocation = ('%%SystemRoot%%\system32\' + $d.Icon);" ^
  "  $lnk.Save();" ^
  "  Write-Host ('  [ok]   ' + $d.Name) }"

if errorlevel 1 (
  echo.
  echo [WARN] Could not create the shortcuts automatically.
  echo        You can make them by hand: right-click start-kiosk.bat,
  echo        choose "Send to" then "Desktop (create shortcut)".
)

echo.
echo ===========================================================================
echo  Done. On your Desktop you now have:
echo.
echo    LUNCH - Start   starts the kiosk and opens the screen
echo    LUNCH - Stop    stops it (the scan screen stops working)
echo    LUNCH - Fix     repairs it if it will not start
echo.
echo  The kiosk still starts by itself when you log in - these are only for
echo  when you want to do it by hand.
echo ===========================================================================
echo.

REM Skip the prompt when another script called us (install-autostart.bat),
REM otherwise its window would hang here waiting for a keypress nobody sees.
if /I not "%~1"=="/quiet" pause
endlocal
