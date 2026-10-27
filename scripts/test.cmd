@echo off
setlocal
cd /d F:\Javis_os
set "TEMP=F:\Javis_os\tmp"
set "TMP=F:\Javis_os\tmp"
set "TMPDIR=F:\Javis_os\tmp"
set "PYTHONPATH=F:\Javis_os\src"
set "PYTHONPYCACHEPREFIX=F:\Javis_os\cache\python"
"F:\Javis_os\.venv\Scripts\python.exe" -B -m unittest discover -s tests -v
set "TEST_RESULT=%ERRORLEVEL%"
pause
exit /b %TEST_RESULT%