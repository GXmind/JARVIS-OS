@echo off
setlocal
cd /d F:\Javis_os
set "TEMP=F:\Javis_os\tmp"
set "TMP=F:\Javis_os\tmp"
set "TMPDIR=F:\Javis_os\tmp"
set "PIP_CACHE_DIR=F:\Javis_os\cache\pip"
set "PYTHONPYCACHEPREFIX=F:\Javis_os\cache\python"
set "PYTHONNOUSERSITE=1"
if not exist "F:\Javis_os\.venv\Scripts\python.exe" (
  echo Run F:\Javis_os\start.cmd first to create the local environment.
  pause
  exit /b 1
)
"F:\Javis_os\.venv\Scripts\python.exe" -B -m pip install --disable-pip-version-check --timeout 20 --retries 1 -r "F:\Javis_os\requirements-audio.txt"
set "INSTALL_RESULT=%ERRORLEVEL%"
pause
exit /b %INSTALL_RESULT%