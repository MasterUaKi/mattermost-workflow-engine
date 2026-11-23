# Author: Oleh Riabtsev
# File: scripts/register_autosync_task.ps1
# Created: 2026-11-23
# Version: 1.0.1

<#
.SYNOPSIS
    Registers a Windows Scheduled Task to run auto_sync_git.ps1 every 5 minutes.
#>

param(
    [string]$TaskName = "MattermostWorkflowEngine-AutoSync",
    [string]$RepoPath = "C:\Entwiklung\mattermost-workflow-engine"
)

$ErrorActionPreference = "Stop"

$ScriptPath = Join-Path $RepoPath "scripts\auto_sync_git.ps1"
if (-not (Test-Path $ScriptPath)) {
    throw "Auto-sync script not found at path: $ScriptPath"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`" -RepoPath `"$RepoPath`" -RunOnce"

$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Automatically checks and pushes repository changes for mattermost-workflow-engine to GitHub every 5 minutes." `
    -Force | Out-Null

Write-Host "Task '$TaskName' successfully registered in Windows Task Scheduler (interval: 5 minutes)."
