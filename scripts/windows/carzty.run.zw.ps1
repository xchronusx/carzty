<#
.SYNOPSIS
    Runs Carzty and drags it back from the dead if it crashes.

.DESCRIPTION
    Starts `python -m carzty` from the repo's .venv and keeps it alive.
      - crashes get restarted with backoff (5s, 10s, 20s... up to 5 min)
      - if it ran fine for 10+ minutes before dying, the backoff resets
      - exit 1 (bad config) and exit 2 (bad token) are NOT restarted, because
        restarting a broken config 400 times just gets you rate limited by Discord
    The bot writes its own log to logs\carzty.log. This launcher logs to C:\Temp.

.PARAMETER NoRestart
    Run once and quit when it stops. Good for debugging.

.PARAMETER MaxRestarts
    Give up after this many restarts. 0 = never give up (default).

.PARAMETER Sync
    Force a slash command re-sync with Discord on startup.

.EXAMPLE
    .\scripts\windows\carzty.run.zw.ps1

.EXAMPLE
    .\scripts\windows\carzty.run.zw.ps1 -NoRestart -Sync

.NOTES
    Author:       Zachary Wright (xchronusx)
    File:         carzty.run.zw.ps1
    Project:      Carzty - https://github.com/xchronusx/carzty
    Purpose:      Launcher / watchdog for the Carzty Discord bot
    License:      MIT
    Disclaimer:   Provided as-is, no warranty. Ctrl+C stops it. That's the whole off switch.
    Requirements: Run carzty.setup.zw.ps1 first (it builds .venv and .env)
#>
##xchronusx

[CmdletBinding()]
param(
    [switch]$NoRestart,
    [int]$MaxRestarts = 0,
    [switch]$Sync
)

$ErrorActionPreference = 'Stop'

#region 0. LOGGING

$LogDir = 'C:\Temp'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir ("carzty.run_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

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

#endregion

#region 1. PREFLIGHT

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$EnvFile = Join-Path $RepoRoot '.env'

Write-Log "==== CARZTY LAUNCHER STARTED ===="
Write-Log "repo: $RepoRoot | launcher log: $LogFile | bot log: $(Join-Path $RepoRoot 'logs\carzty.log')"

try {
    if (-not (Test-Path $VenvPython)) { throw "no .venv found. run .\scripts\windows\carzty.setup.zw.ps1 first" }
    if (-not (Test-Path $EnvFile)) { throw "no .env found. run .\scripts\windows\carzty.setup.zw.ps1 first" }
}
catch {
    Write-Log $_.Exception.Message 'ERROR'
    exit 1
}

#endregion

#region 2. THE LAZARUS PIT

# exit codes that mean "a human needs to fix something", not "try again"
$FatalCodes = @{ 1 = 'bad config - fix .env'; 2 = 'Discord rejected the token - reset it and update .env' }
$Backoff = 5
$MaxBackoff = 300
$Restarts = 0

Push-Location $RepoRoot
try {
    while ($true) {
        $BotArgs = @('-m', 'carzty')
        if ($Sync -and $Restarts -eq 0) { $BotArgs += '--sync' }  # only force the sync on the first launch

        Write-Log ("starting bot (attempt {0})" -f ($Restarts + 1))
        $Started = Get-Date
        & $VenvPython @BotArgs
        $Code = $LASTEXITCODE
        $Uptime = (Get-Date) - $Started
        Write-Log ("bot exited with code {0} after {1:hh\:mm\:ss}" -f $Code, $Uptime) $(if ($Code -eq 0) { 'INFO' } else { 'WARN' })

        if ($FatalCodes.ContainsKey($Code)) {
            Write-Log "not restarting: $($FatalCodes[$Code])" 'ERROR'
            exit $Code
        }
        if ($NoRestart) {
            Write-Log "-NoRestart given, stopping here"
            exit $Code
        }
        if ($MaxRestarts -gt 0 -and $Restarts -ge $MaxRestarts) {
            Write-Log "hit MaxRestarts ($MaxRestarts). it's dead, Jim." 'ERROR'
            exit $Code
        }

        # it ran a good while before dying, so this is a fresh problem. reset the backoff
        if ($Uptime.TotalMinutes -ge 10) { $Backoff = 5 }

        $Restarts++
        Write-Log "restarting in $Backoff second(s). Ctrl+C to bail." 'WARN'
        Start-Sleep -Seconds $Backoff
        $Backoff = [Math]::Min($Backoff * 2, $MaxBackoff)
    }
}
catch {
    Write-Log "launcher blew up: $($_.Exception.Message)" 'ERROR'
    exit 3
}
finally {
    Pop-Location
    Write-Log "==== CARZTY LAUNCHER STOPPED ===="
}

#endregion
##xchronusx
