$ErrorActionPreference = 'Stop'
$projectRoot = 'F:\Javis_os'
if ([IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)) -ne $projectRoot) {
    throw 'Please keep this project at F:\Javis_os.'
}
Set-Location -LiteralPath $projectRoot
foreach ($d in @('tmp','logs','cache','cache\pip')) {
    New-Item -ItemType Directory -Path (Join-Path $projectRoot $d) -Force | Out-Null
}
$env:TEMP = Join-Path $projectRoot 'tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $projectRoot 'cache\pip'
$env:PYTHONPYCACHEPREFIX = Join-Path $projectRoot 'cache\python'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:XDG_CACHE_HOME = Join-Path $projectRoot 'cache'
$env:PYTHONIOENCODING = 'utf-8'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Host 'Creating local Python environment...'
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $projectRoot '.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $projectRoot '.venv')
    } else {
        throw 'Python 3.10+ with tkinter is required. See README.md.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
& $pythonPath -B -c "import sys; assert sys.version_info >= (3,10)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ with tkinter is required.' }
# The default Windows MME audio backend needs no package downloads.
# Hide the helper console; the requested interactive GUI remains visible.
$appProcess = Start-Process -PassThru -FilePath $pythonPath -ArgumentList @('-B', (Join-Path $projectRoot 'main.py')) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'logs\launcher_stdout.log') -RedirectStandardError (Join-Path $projectRoot 'logs\launcher_stderr.log')
$appProcess.Id | Set-Content -LiteralPath (Join-Path $projectRoot 'tmp\gui.pid') -Encoding ascii
Write-Host ('JARVIS started. PID: ' + $appProcess.Id)
