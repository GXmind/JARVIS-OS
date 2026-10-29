@echo off
setlocal
cd /d F:\Javis_os
set "TEMP=F:\Javis_os\tmp"
set "TMP=F:\Javis_os\tmp"
set "PIP_CACHE_DIR=F:\Javis_os\cache\pip"
if not exist tmp mkdir tmp
if not exist .venv\Scripts\python.exe (
  echo Please run start.cmd first to create the local Python environment.
  goto done
)
"F:\Javis_os\.venv\Scripts\python.exe" -B -m pip install -r requirements-wake.txt
if errorlevel 1 goto done
"F:\Javis_os\.venv\Scripts\python.exe" -B scripts\install_wake.py
:done
pause
