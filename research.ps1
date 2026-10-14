$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
if ($env:CRC_PYTHON) {
    & $env:CRC_PYTHON (Join-Path $PSScriptRoot 'research.py') @args
} elseif (Test-Path (Join-Path $PSScriptRoot '.venv\Scripts\python.exe')) {
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'research.py') @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $PSScriptRoot 'research.py') @args
} else {
    & python (Join-Path $PSScriptRoot 'research.py') @args
}
exit $LASTEXITCODE
