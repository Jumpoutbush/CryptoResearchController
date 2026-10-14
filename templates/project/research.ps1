$Entry = Join-Path $PSScriptRoot '..\..\research.ps1'
& $Entry @args
exit $LASTEXITCODE
