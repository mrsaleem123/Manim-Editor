@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-offline-installer.ps1" -InstallerOnly
if errorlevel 1 (
  echo.
  echo RETRY FAILED. Review the error above.
  pause
  exit /b 1
)
echo.
echo BUILD COMPLETE. Open dist-installer to find the Setup EXE.
pause
