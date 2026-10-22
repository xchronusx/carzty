<#
.SYNOPSIS
    Sets up Carzty on Windows. venv, packages, config, the works.

.DESCRIPTION
    Run this once after you download the repo, and again any time you update it.
      1. Finds Python 3.10+ (py launcher first, then python.exe, and it skips the fake
         Microsoft Store one that just opens the Store)
      2. Builds .venv in the repo folder and installs requirements
      3. Runs the setup wizard (`python -m carzty setup`): asks for your bot token,
         checks it with Discord, detects your timezone, offers to lock the bot to you,
         and prints your invite link
      4. Runs `python -m carzty check` so you know it actually works
      5. Asks if you want it to start with Windows, or just start it now

    The one-line installer (carzty.install.zw.ps1) and install.cmd both call this.

.PARAMETER Token
    Bot token. Skip it and the wizard asks with hidden input, which is better because
    then it doesn't end up in your shell history.

.PARAMETER Timezone
    IANA timezone like America/Phoenix. Skip it and the wizard detects it from Windows.

.PARAMETER Dev
    Also install pytest + ruff so you can run the tests.

.PARAMETER Force
    Nuke and rebuild .venv from scratch.

.PARAMETER NoPrompt
    No questions. Skips the wizard if .env already exists (otherwise runs it with defaults, so pass -Token),
    installs Python without asking if it's missing, and skips the "start it?" questions at the end.

.EXAMPLE
    .\scripts\windows\carzty.setup.zw.ps1

.EXAMPLE
    .\scripts\windows\carzty.setup.zw.ps1 -Dev -Force

.NOTES
    Author:       Zachary Wright (xchronusx)
    File:         carzty.setup.zw.ps1
    Project:      Carzty - https://github.com/xchronusx/carzty
    Purpose:      Windows setup for the Carzty Discord bot
    License:      MIT
    Disclaimer:   Provided as-is, no warranty. It touches nothing outside the repo folder and C:\Temp.
    Requirements: Windows 10/11, PowerShell 5.1+ (7 works too), Python 3.10+ (the one-line installer grabs it for you)
#>
##xchronusx

[CmdletBinding()]
param(
    [string]$Token,
    [string]$Timezone,
    [switch]$Dev,
    [switch]$Force,
    [switch]$NoPrompt
)

$ErrorActionPreference = 'Stop'

#region 0. LOGGING

$LogDir = 'C:\Temp'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir ("carzty.setup_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

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

function Read-YesNo {
    param([string]$Question, [bool]$Default = $true)
    $Hint = if ($Default) { '[Y/n]' } else { '[y/N]' }
    while ($true) {
        $Answer = "$(Read-Host "$Question $Hint")".Trim().ToLower()
        if (-not $Answer) { return $Default }
        if ($Answer -in @('y', 'yes')) { return $true }
        if ($Answer -in @('n', 'no')) { return $false }
        Write-Host "  y or n. it's not a trick question." -ForegroundColor DarkGray
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$VenvDir = Join-Path $RepoRoot '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$EnvFile = Join-Path $RepoRoot '.env'

Write-Log "==== CARZTY SETUP STARTED ===="
Write-Log "repo: $RepoRoot"
Write-Log "log:  $LogFile"

#endregion

#region 1. FIND PYTHON

function Test-PythonCandidate {
    # returns "3.12" style version string, or $null if this thing isn't a usable python
    param([string[]]$Command)
    try {
        $Exe = $Command[0]
        $ExtraArgs = @($Command | Select-Object -Skip 1)
        $Out = & $Exe @ExtraArgs -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$Out" -match '^\d+\.\d+$') { return "$Out".Trim() }
    }
    catch { }  # not a python, or not one that works. move along
    return $null
}

function Find-Python {
    $Candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) { $Candidates += , @('py', '-3') }
    $PyExe = Get-Command python -ErrorAction SilentlyContinue
    # the WindowsApps python.exe is a stub that opens the Microsoft Store. no thanks
    if ($PyExe -and $PyExe.Source -notlike '*\WindowsApps\*') { $Candidates += , @($PyExe.Source) }
    # where python.org / winget drop it for a per-user install, in case PATH didn't get the memo
    $UserPythons = Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python3*\python.exe') -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    foreach ($Found in $UserPythons) { $Candidates += , @($Found.FullName) }

    foreach ($Candidate in $Candidates) {
        $Version = Test-PythonCandidate -Command $Candidate
        if ($Version -and ([version]$Version -ge [version]'3.10')) {
            Write-Log ("found python {0} via '{1}'" -f $Version, ($Candidate -join ' ')) 'OK'
            return , $Candidate
        }
        elseif ($Version) {
            Write-Log ("'{0}' is python {1}, need 3.10+. skipping" -f ($Candidate -join ' '), $Version) 'WARN'
        }
    }
    return $null
}

try {
    $Python = Find-Python

    if (-not $Python) {
        $HasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)
        if (-not $HasWinget) {
            throw "No Python 3.10+ found and no winget to grab it with. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again."
        }
        $DoIt = $NoPrompt -or (Read-YesNo "No Python 3.10+ on this machine. Install Python 3.12 with winget (just for your user, no admin)?")
        if (-not $DoIt) { throw "Can't run without Python. Install 3.10+ and run this again." }

        Write-Log "installing Python 3.12 with winget. this takes a minute"
        & winget install --id Python.Python.3.12 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Write-Log "winget exited $LASTEXITCODE, checking if python showed up anyway" 'WARN' }

        # winget updated PATH in the registry, not in this session. reload it
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        $Python = Find-Python
        if (-not $Python) { throw "winget ran but I still can't find Python. Open a new PowerShell window and run this again." }
    }
}
catch {
    Write-Log $_.Exception.Message 'ERROR'
    exit 1
}

#endregion

#region 2. VENV + PACKAGES

try {
    if ($Force -and (Test-Path $VenvDir)) {
        Write-Log "-Force given, burning down the old .venv"
        Remove-Item -Recurse -Force $VenvDir
    }

    if (-not (Test-Path $VenvPython)) {
        Write-Log "creating .venv"
        $PyExe = $Python[0]
        $PyArgs = @($Python | Select-Object -Skip 1) + @('-m', 'venv', $VenvDir)
        & $PyExe @PyArgs
        if ($LASTEXITCODE -ne 0) { throw "python -m venv failed (exit $LASTEXITCODE)" }
    }
    else {
        Write-Log ".venv already there, reusing it"
    }

    Write-Log "upgrading pip"
    & $VenvPython -m pip install --upgrade pip --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed (exit $LASTEXITCODE)" }

    $ReqFile = if ($Dev) { 'requirements-dev.txt' } else { 'requirements.txt' }
    Write-Log "installing $ReqFile"
    & $VenvPython -m pip install -r (Join-Path $RepoRoot $ReqFile) --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
    Write-Log "packages installed" 'OK'
}
catch {
    Write-Log $_.Exception.Message 'ERROR'
    exit 1
}

#endregion

#region 3. THE WIZARD

try {
    Push-Location $RepoRoot
    if ($NoPrompt -and (Test-Path $EnvFile) -and -not $Token -and -not $Timezone) {
        Write-Log ".env exists and -NoPrompt given, skipping the wizard"
    }
    else {
        $WizardArgs = @('-m', 'carzty', 'setup')
        if ($Token) { $WizardArgs += @('--token', $Token.Trim()) }
        if ($Timezone) { $WizardArgs += @('--timezone', $Timezone) }
        if ($NoPrompt) { $WizardArgs += '--yes' }
        Write-Log "starting the setup wizard"
        & $VenvPython @WizardArgs
        $WizardExit = $LASTEXITCODE
        if ($WizardExit -eq 130) { throw "setup cancelled. rerun this whenever you're ready" }
        if ($WizardExit -ne 0) { throw "the wizard didn't finish (exit $WizardExit). rerun this to try again" }
        Write-Log "wizard done, .env written" 'OK'
    }
}
catch {
    Write-Log $_.Exception.Message 'ERROR'
    exit 1
}
finally {
    Pop-Location
}

#endregion

#region 4. SMOKE TEST

try {
    Push-Location $RepoRoot
    Write-Log "running python -m carzty check"
    # 5.1 turns redirected stderr into terminating errors when EAP is Stop. dial it back for this one call
    $ErrorActionPreference = 'Continue'
    $Check = & $VenvPython -m carzty check 2>&1
    $CheckExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    $Check | ForEach-Object { Write-Log "  $_" }
    if ($CheckExit -ne 0) { throw "config check failed (exit $CheckExit). run this again to redo the wizard" }
    Write-Log "config check passed" 'OK'
}
catch {
    Write-Log $_.Exception.Message 'ERROR'
    exit 1
}
finally {
    Pop-Location
}

#endregion

#region 5. START IT?

Write-Log "==== CARZTY SETUP FINISHED ===="

$RunScript = Join-Path $PSScriptRoot 'carzty.run.zw.ps1'
$AutoScript = Join-Path $PSScriptRoot 'carzty.autostart.zw.ps1'

if ($NoPrompt) {
    Write-Host ""
    Write-Host "Run it:             .\scripts\windows\carzty.run.zw.ps1   (or double-click start.cmd)" -ForegroundColor Cyan
    Write-Host "Start with Windows: .\scripts\windows\carzty.autostart.zw.ps1 -Install" -ForegroundColor Cyan
}
else {
    Write-Host ""
    if (Read-YesNo "Start Carzty automatically when you log in to Windows?") {
        & $AutoScript -Install
    }
    elseif (Read-YesNo "Start it now in a new window?") {
        Start-Process powershell.exe -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$RunScript`"") -WorkingDirectory $RepoRoot
        Write-Log "started in a new window. close that window to stop it" 'OK'
    }
    else {
        Write-Host "No problem. Double-click start.cmd (or run .\scripts\windows\carzty.run.zw.ps1) when you're ready." -ForegroundColor Cyan
    }
}

#endregion
##xchronusx
