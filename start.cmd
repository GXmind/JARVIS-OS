@echo off
setlocal
cd /d F:\Javis_os
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "F:\Javis_os\scripts\start.ps1"
if errorlevel 1 (
  echo Startup failed. See F:\Javis_os\README.md and logs.
  pause
)
endlocal