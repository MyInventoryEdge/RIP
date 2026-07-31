@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
"C:\INVENTORY_EDGE\runtime\python314\python.exe" -m rip.console.app
if errorlevel 1 pause
