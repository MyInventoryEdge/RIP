$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

py -m unittest discover -s tests -v
py .\run-rip.py status
py .\run-rip.py observe
py .\run-rip.py ask --help
py -c "from rip.console.app import RipConsole; print('RIP console import OK')"

Write-Host "`nRIP Platform Milestone 0004A verified locally."
