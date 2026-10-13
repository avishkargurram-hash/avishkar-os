<#
.SYNOPSIS
  Installs Layla PC Agent as a persistent, auto-starting background service
  for this Windows account -- replaces the manual Register-ScheduledTask
  setup with a real, repeatable installer.

.DESCRIPTION
  1. Copies LaylaPCAgent.exe (a PyInstaller --onefile --noconsole build of
     layla_pc_agent.py -- no Python install needed on the target machine)
     into %LOCALAPPDATA%\LaylaPCAgent.
  2. Registers a Scheduled Task ("LaylaPCAgent") that starts it at logon,
     using the exact same New-ScheduledTaskAction/Register-ScheduledTask
     structured-cmdlet pattern already proven to work (raw `schtasks /TR`
     with a spaced path silently fails -- do not revert to it).
  3. Removes any older "LaylaPCAgent" task first so re-running this script
     is a safe upgrade path, not a duplicate-task footgun.

  Run this from an elevated or normal PowerShell prompt -- AtLogOn/Limited
  scope does not require admin rights.
#>

$ErrorActionPreference = "Stop"

$InstallDir = Join-Path $env:LOCALAPPDATA "LaylaPCAgent"
$ExeName    = "LaylaPCAgent.exe"
$SourceExe  = Join-Path $PSScriptRoot "dist\$ExeName"
$TaskName   = "LaylaPCAgent"

if (-not (Test-Path $SourceExe)) {
    Write-Error "Could not find $SourceExe -- build it first with: python -m PyInstaller --onefile --noconsole --name LaylaPCAgent layla_pc_agent.py"
    exit 1
}

Write-Host "Installing Layla PC Agent to $InstallDir ..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Path $SourceExe -Destination $InstallDir -Force

# NOTE: deliberately NOT calling Get-ScheduledTask/Unregister-ScheduledTask
# here to check for an existing task first -- Get-ScheduledTask hangs
# indefinitely in some locked-down environments (same class of restriction
# as the Get-CimInstance issue below). Register-ScheduledTask -Force alone
# overwrites an existing task of the same name, so this is still idempotent.

# Also stop any currently-running instance (old exe path or the original
# dev-session pythonw.exe) so the new one doesn't fight it for the MQTT
# client id. NOTE: deliberately NOT using Get-CimInstance/Win32_Process here
# to filter by command line -- it hangs indefinitely in some locked-down
# environments (WMI service restrictions). A blunt Stop-Process by name is
# safe on a personal single-user machine where "pythonw.exe" is only ever
# this agent.
Get-Process -Name "LaylaPCAgent" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "pythonw" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

$exePath = Join-Path $InstallDir $ExeName
$action  = New-ScheduledTaskAction -Execute $exePath
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' (starts at logon, restarts up to 3x on crash)."
Write-Host "Starting it now..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2

$proc = Get-Process -Name "LaylaPCAgent" -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "SUCCESS: Layla PC Agent is running (PID $($proc.Id))."
} else {
    Write-Warning "Task registered but no LaylaPCAgent.exe process was found running -- check Task Scheduler > LaylaPCAgent for errors."
}

Write-Host ""
Write-Host "To uninstall: Unregister-ScheduledTask -TaskName LaylaPCAgent -Confirm:`$false; Remove-Item -Recurse -Force '$InstallDir'"
