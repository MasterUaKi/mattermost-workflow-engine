# Author: Oleh Riabtsev
# File: scripts/auto_sync_git.ps1
# Created: 2026-11-23
# Version: 1.0.1

<#
.SYNOPSIS
    Automatically checks for Git changes in the repository and pushes them to GitHub.
.DESCRIPTION
    Supports two execution modes:
    1. Continuous loop every 300 seconds (5 minutes) - default.
    2. Single pass (-RunOnce) - used by Windows Task Scheduler.
#>

param(
    [string]$RepoPath = "C:\Entwiklung\mattermost-workflow-engine",
    [string]$Branch = "main",
    [int]$IntervalSeconds = 300,
    [switch]$RunOnce
)

$ErrorActionPreference = "Continue"

$LogDir = Join-Path $RepoPath "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir "git_autosync.log"

function Write-SyncLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Line = "[$Timestamp] [$Level] $Message"
    Write-Host $Line
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
}

function Invoke-GitSyncCycle {
    if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
        Write-SyncLog "Directory '$RepoPath' is not an initialized Git repository." "ERROR"
        return
    }

    Set-Location $RepoPath

    # Skip cycle if Git is currently locked by another process (e.g. PyCharm)
    $LockFile = Join-Path $RepoPath ".git\index.lock"
    if (Test-Path $LockFile) {
        Write-SyncLog "Detected .git/index.lock file. Skipping sync cycle." "WARN"
        return
    }

    $StatusOutput = git status --porcelain 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog "Failed to execute git status." "ERROR"
        return
    }

    if ([string]::IsNullOrWhiteSpace(($StatusOutput -join ""))) {
        Write-SyncLog "No changes detected. Push is not required." "INFO"
        return
    }

    git add -A 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog "Failed to stage changes via git add." "ERROR"
        return
    }

    git diff --cached --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-SyncLog "No staged changes left after .gitignore filtering." "INFO"
        return
    }

    $ChangedFiles = (git diff --cached --name-only 2>&1) -join ", "
    $CommitTimestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $CommitMessage = "chore(auto-sync): update project files [$CommitTimestamp]"

    git commit -m $CommitMessage 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog "Failed to create commit." "ERROR"
        return
    }

    git pull --rebase origin $Branch 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog "Failed to execute git pull --rebase origin $Branch. Manual check required." "ERROR"
        return
    }

    git push origin $Branch 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog "Failed to push changes to origin/$Branch." "ERROR"
        return
    }

    Write-SyncLog "Changes successfully pushed to origin/$Branch. Files: $ChangedFiles" "INFO"
}

Write-SyncLog "Starting Git auto-sync service for '$RepoPath' (branch: $Branch, interval: ${IntervalSeconds}s)." "INFO"

if ($RunOnce) {
    Invoke-GitSyncCycle
    exit 0
}

while ($true) {
    Invoke-GitSyncCycle
    Start-Sleep -Seconds $IntervalSeconds
}
