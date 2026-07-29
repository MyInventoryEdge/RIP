$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Installing RIP Platform in editable mode..."
py -m pip install -e .

Write-Host "`nRunning automated tests..."
py -m unittest discover -s tests -v

Write-Host "`nReading RIP foundation..."
rip status

Write-Host "`nChecking deterministic observation..."
rip observe

Write-Host "`nChecking grounded-reasoning command..."
rip ask --help

Write-Host "`nChecking temporary reasoning console..."
py -c "from rip.console.app import RipConsole; print('RIP console import OK')"

Write-Host "`nRIP Platform Milestone 0004A installed and verified."
Write-Host "Run: rip-console"
