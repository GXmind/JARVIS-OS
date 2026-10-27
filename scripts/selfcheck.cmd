@echo off
setlocal
cd /d F:\Javis_os
set "TEMP=F:\Javis_os\tmp"
set "TMP=F:\Javis_os\tmp"
set "PYTHONPYCACHEPREFIX=F:\Javis_os\cache\python"
set "PYTHONPATH=F:\Javis_os\src"
"F:\Javis_os\.venv\Scripts\python.exe" -B "F:\Javis_os\main.py" --self-check %*
set "CHECK_RESULT=%ERRORLEVEL%"
echo.
echo Report: F:\Javis_os\logs\selfcheck.json
pause
exit /b %CHECK_RESULT%