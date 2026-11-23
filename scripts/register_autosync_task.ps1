# Автор: Oleh Riabtsev
# Файл: scripts/register_autosync_task.ps1
# Дата создания: 2026-11-23
# Версия: 1.0.0

<#
.SYNOPSIS
    Регистрирует задачу в Планировщике заданий Windows для запуска auto_sync_git.ps1 каждые 5 минут.
#>

param(
    [string]$TaskName = "MattermostWorkflowEngine-AutoSync",
    [string]$RepoPath = "C:\Entwiklung\mattermost-workflow-engine"
)

$ErrorActionPreference = "Stop"

$ScriptPath = Join-Path $RepoPath "scripts\auto_sync_git.ps1"
if (-not (Test-Path $ScriptPath)) {
    throw "Скрипт автосинхронизации не найден по пути: $ScriptPath"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`" -RepoPath `"$RepoPath`" -RunOnce"

# Запуск сразу после регистрации с повторением каждые 5 минут бессрочно
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
    -Description "Автоматическая проверка и отправка изменений репозитория mattermost-workflow-engine в GitHub каждые 5 минут." `
    -Force | Out-Null

Write-Host "Задача '$TaskName' успешно зарегистрирована в Планировщике заданий Windows (интервал: 5 минут)."
