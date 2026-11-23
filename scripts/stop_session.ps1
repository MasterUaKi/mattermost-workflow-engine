# Author: Oleh Riabtsev
# File: scripts/stop_session.ps1
# Created: 2026-11-23
# Version: 1.0.0

<#
.SYNOPSIS
    Stops background Git auto-sync monitoring, commits and pushes final changes to GitHub,
    and optionally stops local Docker containers at the end of a development session.
#>

param(
    [string]$RepoPath = "C:\Entwiklung\mattermost-workflow-engine",
    [string]$TaskName = "MattermostWorkflowEngine-AutoSync",
    [string]$Branch = "main",
    [string]$ConsoleLang = "",
    [switch]$StopDocker
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

# Localized console messages (ASCII-escaped Unicode for Windows PowerShell 5.1 compatibility)
$Messages = @{
    en = @{
        stopping_task   = "Stopping background Git auto-sync monitoring ('{0}')..."
        task_removed    = "Scheduled task '{0}' unregistered."
        task_not_found  = "Scheduled task '{0}' was not active."
        proc_stopped    = "Stopped {0} running auto_sync_git.ps1 background process(es)."
        lock_wait       = "Waiting for .git/index.lock to be released..."
        staging_files   = "Staging all final session changes..."
        no_changes      = "Working tree is already clean. Nothing new to commit."
        committing      = "Creating final commit: '{0}'..."
        pushing         = "Pushing final commit to origin/{0}..."
        push_ok         = "All changes successfully pushed to GitHub (origin/{0})."
        push_err        = "Failed to push final changes to origin/{0}. Please check Git output above."
        stopping_docker = "Stopping local Docker containers (preserving database and Mattermost volumes)..."
        docker_stopped  = "Local Docker containers stopped."
        session_paused  = "Development session paused. Run '.\scripts\register_autosync_task.ps1' next time to resume 5-minute auto-sync."
    }
    de = @{
        stopping_task   = "Stoppe Hintergrund-Git-Auto-Sync ('{0}')..."
        task_removed    = "Geplante Aufgabe '{0}' wurde entfernt."
        task_not_found  = "Geplante Aufgabe '{0}' war nicht aktiv."
        proc_stopped    = "{0} laufende(r) auto_sync_git.ps1 Hintergrundprozess(e) beendet."
        lock_wait       = "Warte auf Freigabe von .git/index.lock..."
        staging_files   = "Bereite alle abschlie\u00dfenden \u00c4nderungen vor (git add)..."
        no_changes      = "Arbeitsverzeichnis ist bereits sauber. Keine neuen \u00c4nderungen."
        committing      = "Erstelle Abschluss-Commit: '{0}'..."
        pushing         = "Sende Abschluss-Commit an origin/{0}..."
        push_ok         = "Alle \u00c4nderungen erfolgreich nach GitHub (origin/{0}) gesendet."
        push_err        = "Fehler beim Senden an origin/{0}. Bitte Git-Ausgabe pr\u00fcfen."
        stopping_docker = "Stoppe lokale Docker-Container (Datenbank- und Mattermost-Volumes bleiben erhalten)..."
        docker_stopped  = "Lokale Docker-Container wurden gestoppt."
        session_paused  = "Entwicklungssitzung pausiert. Starten Sie beim n\u00e4chsten Mal '.\scripts\register_autosync_task.ps1'."
    }
    ru = @{
        stopping_task   = "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u0444\u043e\u043d\u043e\u0432\u043e\u0433\u043e \u043c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433\u0430 Git ('{0}')..."
        task_removed    = "\u0417\u0430\u0434\u0430\u0447\u0430 \u043f\u043b\u0430\u043d\u0438\u0440\u043e\u0432\u0449\u0438\u043a\u0430 '{0}' \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u0430 \u0438 \u0443\u0434\u0430\u043b\u0435\u043d\u0430."
        task_not_found  = "\u0417\u0430\u0434\u0430\u0447\u0430 \u043f\u043b\u0430\u043d\u0438\u0440\u043e\u0432\u0449\u0438\u043a\u0430 '{0}' \u0443\u0436\u0435 \u0431\u044b\u043b\u0430 \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u0430."
        proc_stopped    = "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e \u0444\u043e\u043d\u043e\u0432\u044b\u0445 \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u043e\u0432 auto_sync_git.ps1: {0}."
        lock_wait       = "\u041e\u0436\u0438\u0434\u0430\u043d\u0438\u0435 \u043e\u0441\u0432\u043e\u0431\u043e\u0436\u0434\u0435\u043d\u0438\u044f .git/index.lock..."
        staging_files   = "\u0418\u043d\u0434\u0435\u043a\u0441\u0430\u0446\u0438\u044f \u0432\u0441\u0435\u0445 \u0444\u0438\u043d\u0430\u043b\u044c\u043d\u044b\u0445 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0439 \u0441\u0435\u0441\u0441\u0438\u0438 (git add -A)..."
        no_changes      = "\u0412\u0441\u0435 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f \u0443\u0436\u0435 \u0437\u0430\u0444\u0438\u043a\u0441\u0438\u0440\u043e\u0432\u0430\u043d\u044b. \u041d\u043e\u0432\u044b\u0445 \u0444\u0430\u0439\u043b\u043e\u0432 \u043d\u0435\u0442."
        committing      = "\u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435 \u0444\u0438\u043d\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u043a\u043e\u043c\u043c\u0438\u0442\u0430: '{0}'..."
        pushing         = "\u041e\u0442\u043f\u0440\u0430\u0432\u043a\u0430 \u0434\u0430\u043d\u043d\u044b\u0445 \u043d\u0430 GitHub (origin/{0})..."
        push_ok         = "\u0412\u0441\u0435 \u0444\u0430\u0439\u043b\u044b \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u044b \u0432 \u0440\u0435\u043f\u043e\u0437\u0438\u0442\u043e\u0440\u0438\u0439 (origin/{0})."
        push_err        = "\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u043a\u0435 \u0432 origin/{0}. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0432\u044b\u0432\u043e\u0434 Git \u0432\u044b\u0448\u0435."
        stopping_docker = "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0445 Docker-\u043a\u043e\u043d\u0442\u0435\u0439\u043d\u0435\u0440\u043e\u0432 (\u0441 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u0435\u043c \u0442\u043e\u043c\u043e\u0432 \u0411\u0414 \u0438 Mattermost)..."
        docker_stopped  = "\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0435 Docker-\u043a\u043e\u043d\u0442\u0435\u0439\u043d\u0435\u0440\u044b \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u044b."
        session_paused  = "\u0420\u0430\u0431\u043e\u0442\u0430 \u043f\u043e \u043f\u0440\u043e\u0435\u043a\u0442\u0443 \u043f\u0440\u0438\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430. \u0414\u043b\u044f \u0432\u043e\u0437\u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f \u0430\u0432\u0442\u043e\u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u0438 \u0432 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0440\u0430\u0437 \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 '.\scripts\register_autosync_task.ps1'."
    }
}

function Get-Msg {
    param([string]$Key, [object[]]$FormatArgs = @())
    $Template = [regex]::Unescape($Messages[$ActiveLang][$Key])
    if ($FormatArgs.Count -gt 0) { return ($Template -f $FormatArgs) }
    return $Template
}

$LogDir = Join-Path $RepoPath "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir "git_autosync.log"

function Write-SessionLog {
    param([string]$Message, [string]$Level = "INFO")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Line = "[$Timestamp] [$Level] $Message"
    Write-Host $Line
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
}

# 1. Disable Windows Scheduled Task and stop any running auto_sync_git.ps1 processes
Write-SessionLog (Get-Msg "stopping_task" @($TaskName)) "INFO"

$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-SessionLog (Get-Msg "task_removed" @($TaskName)) "INFO"
} else {
    Write-SessionLog (Get-Msg "task_not_found" @($TaskName)) "INFO"
}

$RunningSyncProcs = Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like "*auto_sync_git.ps1*" }

$StoppedCount = 0
foreach ($Proc in $RunningSyncProcs) {
    Stop-Process -Id $Proc.ProcessId -Force -ErrorAction SilentlyContinue
    $StoppedCount++
}
if ($StoppedCount -gt 0) {
    Write-SessionLog (Get-Msg "proc_stopped" @($StoppedCount)) "INFO"
}

# 2. Wait briefly if a Git lock file was left by a just-terminated sync process
Set-Location $RepoPath
$LockFile = Join-Path $RepoPath ".git\index.lock"
for ($i = 1; $i -le 5; $i++) {
    if (-not (Test-Path $LockFile)) { break }
    Write-SessionLog (Get-Msg "lock_wait") "WARN"
    Start-Sleep -Seconds 1
}

# 3. Stage all remaining changes (including scripts/stop_session.ps1) and push final commit
Write-SessionLog (Get-Msg "staging_files") "INFO"
git add -A 2>&1 | Out-Null

git diff --cached --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-SessionLog (Get-Msg "no_changes") "INFO"
} else {
    $CommitDate = Get-Date -Format "yyyy-MM-dd HH:mm"
    $CommitMsg = "chore(session-end): finalize visual workflow studio, tests, CI, and stop auto-sync [$CommitDate]"
    Write-SessionLog (Get-Msg "committing" @($CommitMsg)) "INFO"

    git commit -m $CommitMsg
    if ($LASTEXITCODE -ne 0) {
        Write-SessionLog (Get-Msg "push_err" @($Branch)) "ERROR"
        exit 1
    }

    Write-SessionLog (Get-Msg "pushing" @($Branch)) "INFO"
    git pull --rebase origin $Branch
    git push origin $Branch
    if ($LASTEXITCODE -ne 0) {
        Write-SessionLog (Get-Msg "push_err" @($Branch)) "ERROR"
        exit 1
    }

    Write-SessionLog (Get-Msg "push_ok" @($Branch)) "INFO"
}

# 4. Optionally stop local Docker containers while preserving PostgreSQL & Mattermost volumes
if ($StopDocker) {
    Write-SessionLog (Get-Msg "stopping_docker") "INFO"
    docker compose down
    Write-SessionLog (Get-Msg "docker_stopped") "INFO"
}

Write-SessionLog (Get-Msg "session_paused") "INFO"