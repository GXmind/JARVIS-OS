@echo off
setlocal
cd /d F:\Javis_os
set "TEMP=F:\Javis_os\tmp"
set "TMP=F:\Javis_os\tmp"
"F:\Javis_os\.venv\Scripts\python.exe" -B scripts\install_hand.py
pause
