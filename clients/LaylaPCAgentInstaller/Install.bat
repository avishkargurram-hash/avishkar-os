@echo off
REM Double-click this to install Layla PC Agent -- no PowerShell knowledge needed.
REM -ExecutionPolicy Bypass applies only to this one launch, not system-wide.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-LaylaPCAgent.ps1"
pause
