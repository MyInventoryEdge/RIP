$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
py -m unittest discover -s tests -v
py .\run-rip.py status
