$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
& "C:\INVENTORY_EDGE\runtime\python314\python.exe" -m rip.console.app
