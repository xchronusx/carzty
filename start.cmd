@echo off
rem ##xchronusx
rem  Double-click me to run Carzty. Close this window to stop it.
rem  Want it to start with Windows instead? scripts\windows\carzty.autostart.zw.ps1 -Install
rem  Author: Zachary Wright (xchronusx)
cd /d "%~dp0"
title Carzty
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\carzty.run.zw.ps1" %*
echo.
pause
rem ##xchronusx
