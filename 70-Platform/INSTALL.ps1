$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Installing RIP Platform in editable mode..."
py -m pip install -e .

Write-Host "`nRunning automated tests..."
py -m unittest discover -s tests -v

Write-Host "`nReading RIP foundation..."
py .\run-rip.py status

Write-Host "`nRIP Platform Milestone 0001 installed and verified."
