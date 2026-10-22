<#
.SYNOPSIS
    One-line Carzty installer for Windows. Paste, answer a few questions, done.

.DESCRIPTION
    Meant to be run straight from GitHub:

        irm https://raw.githubusercontent.com/xchronusx/carzty/main/scripts/windows/carzty.install.zw.ps1 | iex

    What it does:
      1. Downloads Carzty into %USERPROFILE%\Carzty (no git needed)
      2. Hands off to carzty.setup.zw.ps1, which grabs Python with winget if you don't have it,
         builds the venv, runs the setup wizard (token, timezone, tone, invite link) and asks
         if you want it to start with Windows

    Run it again later to update. Your .env, data and logs don't get touched.
    Already cloned it with git? Then it does a `git pull` instead of downloading.

.PARAMETER InstallDir
    Where to put it. Default %USERPROFILE%\Carzty, or $env:CARZTY_DIR if you set that.

.PARAMETER Branch
    Which branch to grab. Default main.

.EXAMPLE
    irm https://raw.githubusercontent.com/xchronusx/carzty/main/scripts/windows/carzty.install.zw.ps1 | iex

.EXAMPLE
    # custom folder
    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/xchronusx/carzty/main/scripts/windows/carzty.install.zw.ps1))) -InstallDir D:\Bots\Carzty

.NOTES
    Author:       Zachary Wright (xchronusx)
    File:         carzty.install.zw.ps1
    Project:      Carzty - https://github.com/xchronusx/carzty
    Purpose:      Download + set up Carzty on Windows in one shot
    License:      MIT
    Disclaimer:   Provided as-is, no warranty. Read a script before you pipe it into iex. Yes, this one too.
    Requirements: Windows 10/11, PowerShell 5.1+. Python gets installed for you (winget) if it's missing.
#>
##xchronusx

param(
    [string]$InstallDir = $(if ($env:CARZTY_DIR) { $env:CARZTY_DIR } else { Join-Path $env:USERPROFILE 'Carzty' }),
    [string]$Branch = 'main'
)

# everything lives in a script block so `irm | iex` doesn't leave our settings lying around in your session,
# and so nothing in here can `exit` and close your PowerShell window on you
& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'  # the 5.1 progress bar makes downloads 10x slower. not kidding
    $Repo = 'xchronusx/carzty'

    #region 0. LOGGING

    $LogDir = 'C:\Temp'
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $LogFile = Join-Path $LogDir ("carzty.install_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

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

    Write-Host ""
    Write-Host "  Carzty installer" -ForegroundColor Cyan
    Write-Host "  a Discord bot that nags you until you do the thing" -ForegroundColor DarkGray
    Write-Host ""
    Write-Log "==== CARZTY INSTALL STARTED ===="
    Write-Log "installing to $InstallDir"

    #endregion

    #region 1. GET THE CODE

    try {
        $IsGitCheckout = Test-Path (Join-Path $InstallDir '.git')
        $HasGit = [bool](Get-Command git -ErrorAction SilentlyContinue)

        if ($IsGitCheckout -and $HasGit) {
            Write-Log "found a git checkout, pulling the latest"
            & git -C $InstallDir pull --ff-only
            if ($LASTEXITCODE -ne 0) { throw "git pull failed. sort out your local changes and run this again" }
        }
        else {
            # TLS 1.2 or GitHub won't talk to Windows PowerShell 5.1
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

            $ZipUrl = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"
            $Stage = Join-Path ([IO.Path]::GetTempPath()) ("carzty_{0}" -f [guid]::NewGuid().ToString('N'))
            $ZipFile = "$Stage.zip"
            Write-Log "downloading $ZipUrl"
            Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipFile -UseBasicParsing

            Write-Log "unpacking"
            Expand-Archive -Path $ZipFile -DestinationPath $Stage -Force
            $Src = Get-ChildItem -Path $Stage -Directory | Select-Object -First 1
            if (-not $Src) { throw "the download was empty. GitHub having a day? try again in a minute" }

            New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
            # overwrite the code, leave .env / data / logs / .venv alone (they're not in the zip anyway).
            # file by file, because Copy-Item -Recurse into an existing folder has opinions about nesting,
            # and robocopy isn't on everybody's PATH
            $SrcRoot = $Src.FullName.TrimEnd('\', '/')
            $Copied = 0
            foreach ($File in Get-ChildItem -Path $SrcRoot -Recurse -File -Force) {
                $Relative = $File.FullName.Substring($SrcRoot.Length + 1)
                $Dest = Join-Path $InstallDir $Relative
                $DestDir = Split-Path -Path $Dest -Parent
                if (-not (Test-Path -LiteralPath $DestDir)) { New-Item -ItemType Directory -Path $DestDir -Force | Out-Null }
                Copy-Item -LiteralPath $File.FullName -Destination $Dest -Force
                # downloaded files get the "came from the internet" flag, which makes RemoteSigned refuse to run them
                Unblock-File -LiteralPath $Dest -ErrorAction SilentlyContinue
                $Copied++
            }
            Remove-Item -Path $Stage, $ZipFile -Recurse -Force -ErrorAction SilentlyContinue
            Write-Log "code's in place ($Copied files)" 'OK'
        }
    }
    catch {
        Write-Log "couldn't get the code: $($_.Exception.Message)" 'ERROR'
        return
    }

    #endregion

    #region 2. SETUP

    try {
        $Setup = Join-Path $InstallDir 'scripts\windows\carzty.setup.zw.ps1'
        if (-not (Test-Path $Setup)) { throw "setup script missing at $Setup. the download looks broken" }

        # new process with -ExecutionPolicy Bypass, because the default policy on a fresh Windows box blocks .ps1 files
        $Shell = (Get-Process -Id $PID).Path
        Write-Log "handing off to setup"
        & $Shell -NoProfile -ExecutionPolicy Bypass -File $Setup
        if ($LASTEXITCODE -ne 0) { throw "setup didn't finish (exit $LASTEXITCODE). fix whatever it complained about and run the installer again" }
    }
    catch {
        Write-Log $_.Exception.Message 'ERROR'
        Write-Log "log: $LogFile"
        return
    }

    #endregion

    #region 3. DONE

    Write-Log "==== CARZTY INSTALL FINISHED ====" 'OK'
    Write-Host ""
    Write-Host "  Carzty lives in: $InstallDir" -ForegroundColor Cyan
    Write-Host "  Start it:        double-click start.cmd in that folder"
    Write-Host "  Change settings: double-click install.cmd in that folder (reruns the wizard), or edit .env"
    Write-Host "  Update:          run this same one-liner again"
    Write-Host "  Uninstall:       $InstallDir\scripts\windows\carzty.autostart.zw.ps1 -Remove, then delete the folder"
    Write-Host ""

    #endregion
}
##xchronusx
