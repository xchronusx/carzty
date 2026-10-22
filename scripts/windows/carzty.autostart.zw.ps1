<#
.SYNOPSIS
    Makes Carzty start with Windows (or stops it from doing that).

.DESCRIPTION
    Registers a Windows Scheduled Task called "Carzty" that runs carzty.run.zw.ps1
    hidden in the background. The run script already restarts the bot if it crashes,
    and the scheduled task restarts the run script if THAT dies. Belt and suspenders.

    Two flavors:
      default      starts when YOU log on, runs as you. no admin needed.
      -AtStartup   starts when the machine boots, runs as SYSTEM, even if nobody logs in.
                   needs an elevated (admin) PowerShell. good for an always-on box.

.PARAMETER Install
    Create (or replace) the scheduled task and start it.

.PARAMETER Remove
    Stop and delete the scheduled task. The bot files are left alone.

.PARAMETER Status
    Show whether it's registered, when it last ran, and what it returned.

.PARAMETER AtStartup
    With -Install: run at boot as SYSTEM instead of at logon as you.

.EXAMPLE
    .\scripts\windows\carzty.autostart.zw.ps1 -Install

.EXAMPLE
    .\scripts\windows\carzty.autostart.zw.ps1 -Install -AtStartup   # from an admin prompt

.EXAMPLE
    .\scripts\windows\carzty.autostart.zw.ps1 -Remove

.NOTES
    Author:       Zachary Wright (xchronusx)
    File:         carzty.autostart.zw.ps1
    Project:      Carzty - https://github.com/xchronusx/carzty
    Purpose:      Register / remove the Carzty scheduled task on Windows
    License:      MIT
    Disclaimer:   Provided as-is, no warranty. Only touches the one scheduled task named "Carzty".
    Requirements: Windows 10/11, PowerShell 5.1+, carzty.setup.zw.ps1 already run. Admin only for -AtStartup.
#>
##xchronusx

[CmdletBinding(DefaultParameterSetName = 'Status')]
param(
    [Parameter(ParameterSetName = 'Install', Mandatory)][switch]$Install,
    [Parameter(ParameterSetName = 'Install')][switch]$AtStartup,
    [Parameter(ParameterSetName = 'Remove', Mandatory)][switch]$Remove,
    [Parameter(ParameterSetName = 'Status')][switch]$Status
)

$ErrorActionPreference = 'Stop'

#region 0. LOGGING

$LogDir = 'C:\Temp'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir ("carzty.autostart_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

function Write-Log {
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR', 'OK')][string]$Level = 'INFO'
    )
    $Line = "{0} [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Add-Content -Path $LogFile -Value $Line
    $Color = switch ($Level) { 'WARN' { 'Yellow' } 'ERROR' { 'Red' } 'OK' { 'Green' } default { 'Gray' } }
    Write-Host $Line -ForegroundColor $Color
}

$TaskName = 'Carzty'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$RunScript = Join-Path $PSScriptRoot 'carzty.run.zw.ps1'

function Test-IsAdmin {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($Identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

Write-Log ("==== CARZTY AUTOSTART ({0}) STARTED ====" -f $PSCmdlet.ParameterSetName.ToUpper())

#endregion

#region 1. INSTALL

if ($Install) {
    try {
        if (-not (Test-Path (Join-Path $RepoRoot '.venv\Scripts\python.exe'))) {
            throw "no .venv yet. run .\scripts\windows\carzty.setup.zw.ps1 first"
        }
        if ($AtStartup -and -not (Test-IsAdmin)) {
            throw "-AtStartup runs as SYSTEM, which needs an admin PowerShell. right click -> Run as administrator"
        }

        $Action = New-ScheduledTaskAction `
            -Execute 'powershell.exe' `
            -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`"" -f $RunScript) `
            -WorkingDirectory $RepoRoot

        if ($AtStartup) {
            $Trigger = New-ScheduledTaskTrigger -AtStartup
            $Principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
            $Flavor = 'at boot, as SYSTEM'
        }
        else {
            $Me = "$env:USERDOMAIN\$env:USERNAME"
            $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $Me
            $Principal = New-ScheduledTaskPrincipal -UserId $Me -LogonType Interactive -RunLevel Limited
            $Flavor = "at logon, as $Me"
        }

        # no time limit, restart the launcher if it dies, don't care about batteries
        $Settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -ExecutionTimeLimit ([TimeSpan]::Zero) `
            -RestartCount 999 `
            -RestartInterval (New-TimeSpan -Minutes 1) `
            -MultipleInstances IgnoreNew

        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Write-Log "task '$TaskName' already exists, replacing it"
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }

        Register-ScheduledTask `
            -TaskName $TaskName `
            -Description 'Carzty Discord reminder bot - https://github.com/xchronusx/carzty' `
            -Action $Action `
            -Trigger $Trigger `
            -Principal $Principal `
            -Settings $Settings | Out-Null

        Start-ScheduledTask -TaskName $TaskName
        Write-Log "installed and started ($Flavor). logs: C:\Temp\carzty.run_*.log and $RepoRoot\logs\carzty.log" 'OK'
    }
    catch {
        Write-Log $_.Exception.Message 'ERROR'
        exit 1
    }
}

#endregion

#region 2. REMOVE

if ($Remove) {
    try {
        if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
            Write-Log "no task named '$TaskName'. nothing to remove" 'WARN'
        }
        else {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Log "removed '$TaskName'. Carzty won't start on its own anymore" 'OK'
            # Stop-ScheduledTask kills the launcher, but python can outlive it. find the straggler
            $Strays = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
                Where-Object { $_.CommandLine -like '*-m carzty*' -and $_.ExecutablePath -like "$RepoRoot*" }
            foreach ($Stray in $Strays) {
                Write-Log "stopping leftover bot process $($Stray.ProcessId)"
                Stop-Process -Id $Stray.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
    }
    catch {
        Write-Log $_.Exception.Message 'ERROR'
        exit 1
    }
}

#endregion

#region 3. STATUS

if ($PSCmdlet.ParameterSetName -eq 'Status') {
    try {
        $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $Task) {
            Write-Log "not installed. use -Install to make Carzty start with Windows" 'WARN'
        }
        else {
            $Info = Get-ScheduledTaskInfo -TaskName $TaskName
            Write-Log ("state: {0} | runs as: {1}" -f $Task.State, $Task.Principal.UserId)
            Write-Log ("last run: {0} | last result: 0x{1:X}" -f $Info.LastRunTime, $Info.LastTaskResult)
            $Running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
                Where-Object { $_.CommandLine -like '*-m carzty*' }
            if ($Running) { Write-Log ("bot process running (pid {0})" -f (($Running | ForEach-Object ProcessId) -join ', ')) 'OK' }
            else { Write-Log "bot process is NOT running right now" 'WARN' }
        }
    }
    catch {
        Write-Log $_.Exception.Message 'ERROR'
        exit 1
    }
}

#endregion

Write-Log "==== CARZTY AUTOSTART FINISHED ===="
##xchronusx
