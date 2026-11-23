# Author: Oleh Riabtsev
# File: scripts/auto_sync_git.ps1
# Created: 2026-11-23
# Version: 1.1.0

<#
.SYNOPSIS
    Automatically checks for Git changes in the repository and pushes them to GitHub.
.DESCRIPTION
    Supports configurable console/log output languages (en, de, ru) via -ConsoleLang or .env (CONSOLE_LANG).
    Execution modes:
    1. Continuous loop every 300 seconds (5 minutes) - default.
    2. Single pass (-RunOnce) - used by Windows Task Scheduler.
#>

param(
    [string]$RepoPath = "C:\Entwiklung\mattermost-workflow-engine",
    [string]$Branch = "main",
    [int]$IntervalSeconds = 300,
    [string]$ConsoleLang = "",
    [switch]$RunOnce
)

$ErrorActionPreference = "Continue"

function Resolve-ConsoleLang {
    param([string]$ExplicitLang, [string]$ProjectRoot)

    $Supported = @("en", "de", "ru")
    if ($ExplicitLang -and ($Supported -contains $ExplicitLang.ToLower())) {
        return $ExplicitLang.ToLower()
    }

    $EnvFile = Join-Path $ProjectRoot ".env"
    if (Test-Path $EnvFile) {
        foreach ($Line in Get-Content -Path $EnvFile -Encoding UTF8) {
            if ($Line -match '^\s*CONSOLE_LANG\s*=\s*["'']?([a-zA-Z]{2})["'']?\s*$') {
                $Candidate = $Matches[1].ToLower()
                if ($Supported -contains $Candidate) {
                    return $Candidate
                }
            }
        }
    }

    return "en"
}

$ActiveLang = Resolve-ConsoleLang -ExplicitLang $ConsoleLang -ProjectRoot $RepoPath

# Localized console/log messages (ASCII-escaped Unicode for Windows PowerShell 5.1 compatibility)
$Messages = @{
    en = @{
        start_service   = "Starting Git auto-sync service for '{0}' (branch: {1}, interval: {2}s)."
        not_a_repo      = "Directory '{0}' is not an initialized Git repository."
        lock_detected   = "Detected .git/index.lock file. Skipping sync cycle."
        status_failed   = "Failed to execute git status."
        no_changes      = "No changes detected. Push is not required."
        add_failed      = "Failed to stage changes via git add."
        nothing_staged  = "No staged changes left after .gitignore filtering."
        commit_failed   = "Failed to create commit."
        pull_failed     = "Failed to execute git pull --rebase origin {0}. Manual check required."
        push_failed     = "Failed to push changes to origin/{0}."
        push_success    = "Changes successfully pushed to origin/{0}. Files: {1}"
    }
    de = @{
        start_service   = "Git Auto-Sync-Dienst f\u00fcr '{0}' gestartet (Branch: {1}, Intervall: {2}s)."
        not_a_repo      = "Verzeichnis '{0}' ist kein initialisiertes Git-Repository."
        lock_detected   = "Datei .git/index.lock erkannt. Synchronisierungszyklus \u00fcbersprungen."
        status_failed   = "Fehler beim Ausf\u00fchren von git status."
        no_changes      = "Keine \u00c4nderungen erkannt. Push nicht erforderlich."
        add_failed      = "Fehler beim Bereitstellen der \u00c4nderungen \u00fcber git add."
        nothing_staged  = "Nach der .gitignore-Filterung sind keine \u00c4nderungen zum Committen vorhanden."
        commit_failed   = "Commit konnte nicht erstellt werden."
        pull_failed     = "Fehler bei git pull --rebase origin {0}. Manuelle Pr\u00fcfung erforderlich."
        push_failed     = "Fehler beim Pushen der \u00c4nderungen nach origin/{0}."
        push_success    = "\u00c4nderungen erfolgreich nach origin/{0} gesendet. Dateien: {1}"
    }
    ru = @{
        start_service   = "\u0417\u0430\u043f\u0443\u0441\u043a \u0441\u043b\u0443\u0436\u0431\u044b \u0430\u0432\u0442\u043e\u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u0438 Git \u0434\u043b\u044f '{0}' (\u0432\u0435\u0442\u043a\u0430: {1}, \u0438\u043d\u0442\u0435\u0440\u0432\u0430\u043b: {2}\u0441)."
        not_a_repo      = "\u041a\u0430\u0442\u0430\u043b\u043e\u0433 '{0}' \u043d\u0435 \u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0438\u043d\u0438\u0446\u0438\u0430\u043b\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u043c Git-\u0440\u0435\u043f\u043e\u0437\u0438\u0442\u043e\u0440\u0438\u0435\u043c."
        lock_detected   = "\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d \u0444\u0430\u0439\u043b \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0438 .git/index.lock. \u0426\u0438\u043a\u043b \u043f\u0440\u043e\u043f\u0443\u0449\u0435\u043d."
        status_failed   = "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0432\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u044c git status."
        no_changes      = "\u0418\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0439 \u043d\u0435 \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u043e. \u041e\u0442\u043f\u0440\u0430\u0432\u043a\u0430 \u043d\u0435 \u0442\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f."
        add_failed      = "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0440\u043e\u0438\u043d\u0434\u0435\u043a\u0441\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f \u0447\u0435\u0440\u0435\u0437 git add."
        nothing_staged  = "\u041f\u043e\u0441\u043b\u0435 \u0444\u0438\u043b\u044c\u0442\u0440\u0430\u0446\u0438\u0438 .gitignore \u043d\u0435\u0442 \u0444\u0430\u0439\u043b\u043e\u0432 \u0434\u043b\u044f \u043a\u043e\u043c\u043c\u0438\u0442\u0430."
        commit_failed   = "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043a\u043e\u043c\u043c\u0438\u0442."
        pull_failed     = "\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0438 git pull --rebase origin {0}. \u0422\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f \u0440\u0443\u0447\u043d\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430."
        push_failed     = "\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u043a\u0435 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0439 \u0432 origin/{0}."
        push_success    = "\u0418\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u044b \u0432 origin/{0}. \u0424\u0430\u0439\u043b\u044b: {1}"
    }
}

function Get-LocalizedLogText {
    param([string]$Key, [object[]]$FormatArgs = @())
    $Template = [regex]::Unescape($Messages[$ActiveLang][$Key])
    if ($FormatArgs.Count -gt 0) {
        return ($Template -f $FormatArgs)
    }
    return $Template
}

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
        Write-SyncLog (Get-LocalizedLogText "not_a_repo" @($RepoPath)) "ERROR"
        return
    }

    Set-Location $RepoPath

    # Skip cycle if Git is currently locked by another process (e.g. PyCharm)
    $LockFile = Join-Path $RepoPath ".git\index.lock"
    if (Test-Path $LockFile) {
        Write-SyncLog (Get-LocalizedLogText "lock_detected") "WARN"
        return
    }

    $StatusOutput = git status --porcelain 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog (Get-LocalizedLogText "status_failed") "ERROR"
        return
    }

    if ([string]::IsNullOrWhiteSpace(($StatusOutput -join ""))) {
        Write-SyncLog (Get-LocalizedLogText "no_changes") "INFO"
        return
    }

    git add -A 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog (Get-LocalizedLogText "add_failed") "ERROR"
        return
    }

    git diff --cached --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-SyncLog (Get-LocalizedLogText "nothing_staged") "INFO"
        return
    }

    $ChangedFiles = (git diff --cached --name-only 2>&1) -join ", "
    $CommitTimestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $CommitMessage = "chore(auto-sync): update project files [$CommitTimestamp]"

    git commit -m $CommitMessage 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog (Get-LocalizedLogText "commit_failed") "ERROR"
        return
    }

    git pull --rebase origin $Branch 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog (Get-LocalizedLogText "pull_failed" @($Branch)) "ERROR"
        return
    }

    git push origin $Branch 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog (Get-LocalizedLogText "push_failed" @($Branch)) "ERROR"
        return
    }

    Write-SyncLog (Get-LocalizedLogText "push_success" @($Branch, $ChangedFiles)) "INFO"
}

Write-SyncLog (Get-LocalizedLogText "start_service" @($RepoPath, $Branch, $IntervalSeconds)) "INFO"

if ($RunOnce) {
    Invoke-GitSyncCycle
    exit 0
}

while ($true) {
    Invoke-GitSyncCycle
    Start-Sleep -Seconds $IntervalSeconds
}
