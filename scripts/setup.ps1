param(
    [switch]$InitGit,
    [switch]$InstallPdfTools
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$BootstrapArgs = @((Join-Path $PSScriptRoot 'bootstrap.py'))
if ($InitGit) { $BootstrapArgs += '--init-git' }
if ($InstallPdfTools) { $BootstrapArgs += '--install-pdf-tools' }
if ($env:CRC_PYTHON) {
    & $env:CRC_PYTHON @BootstrapArgs
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @BootstrapArgs
} else {
    & python @BootstrapArgs
}
exit $LASTEXITCODE
