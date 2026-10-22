@echo off
rem ##xchronusx
rem  Double-click me. Sets up Carzty right here in this folder:
rem  grabs Python if you need it, installs packages, asks for your bot token, done.
rem  Run me again any time to change settings or after updating.
rem  Author: Zachary Wright (xchronusx)
cd /d "%~dp0"
rem files from a downloaded zip get flagged as "from the internet". unflag ours so powershell will run them
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%~dp0' -Recurse -File | Where-Object { $_.FullName -notlike '*\.venv\*' } | Unblock-File -ErrorAction SilentlyContinue"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\carzty.setup.zw.ps1" %*
echo.
pause
rem ##xchronusx
