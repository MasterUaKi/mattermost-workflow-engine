# Автор: Oleh Riabtsev
# Файл: scripts/auto_sync_git.ps1
# Дата создания: 2026-11-23
# Версия: 1.0.0

<#
.SYNOPSIS
    Автоматически проверяет наличие изменений в Git-репозитории и отправляет их на GitHub.
.DESCRIPTION
    Поддерживает два режима работы:
    1. Непрерывный цикл с интервалом 300 секунд (5 минут) — по умолчанию.
    2. Однократный проход (-RunOnce) — для запуска через Планировщик заданий Windows.
#>

param(
    [string]$RepoPath = "C:\Entwiklung\mattermost-workflow-engine",
    [string]$Branch = "main",
    [int]$IntervalSeconds = 300,
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"

# Каталог и файл для журналирования работы автосинхронизации (исключен через .gitignore)
$LogDir = Join-Path $RepoPath "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir "git_autosync.log"

function Write-SyncLog {
    param([string]$Message, [string]$Level = "INFO")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Line = "[$Timestamp] [$Level] $Message"
    Write-Host $Line
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
}

function Invoke-GitSyncCycle {
    if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
        Write-SyncLog "Каталог '$RepoPath' не является инициализированным Git-репозиторием." "ERROR"
        return
    }

    Set-Location $RepoPath

    # Пропускаем цикл, если Git сейчас занят другой операцией (например, коммитом из PyCharm)
    $LockFile = Join-Path $RepoPath ".git\index.lock"
    if (Test-Path $LockFile) {
        Write-SyncLog "Обнаружен файл блокировки .git/index.lock. Цикл пропущен." "WARN"
        return
    }

    # Проверяем наличие неотслеживаемых или измененных файлов
    $StatusOutput = git status --porcelain
    if ([string]::IsNullOrWhiteSpace(($StatusOutput -join ""))) {
        Write-SyncLog "Изменений не обнаружено. Отправка не требуется." "INFO"
        return
    }

    try {
        # Индексируем все изменения с учетом правил .gitignore
        git add -A

        # Повторно проверяем индекс после применения .gitignore
        git diff --cached --quiet
        if ($LASTEXITCODE -eq 0) {
            Write-SyncLog "После фильтрации .gitignore нет файлов для коммита." "INFO"
            return
        }

        $ChangedFiles = (git diff --cached --name-only) -join ", "
        $CommitTimestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $CommitMessage = "chore(auto-sync): update project files [$CommitTimestamp]"

        git commit -m $CommitMessage | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-SyncLog "Не удалось создать коммит." "ERROR"
            return
        }

        # Синхронизируемся с удаленной веткой перед отправкой во избежание конфликтов
        git pull --rebase origin $Branch | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-SyncLog "Ошибка при выполнении git pull --rebase origin $Branch. Требуется ручная проверка." "ERROR"
            return
        }

        git push origin $Branch | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-SyncLog "Ошибка при отправке изменений в origin/$Branch." "ERROR"
            return
        }

        Write-SyncLog "Изменения успешно отправлены в origin/$Branch. Файлы: $ChangedFiles" "INFO"
    }
    catch {
        Write-SyncLog "Исключение при синхронизации: $($_.Exception.Message)" "ERROR"
    }
}

Write-SyncLog "Запуск службы автосинхронизации Git для '$RepoPath' (ветка: $Branch, интервал: $IntervalSeconds сек)." "INFO"

if ($RunOnce) {
    Invoke-GitSyncCycle
    exit 0
}

while ($true) {
    Invoke-GitSyncCycle
    Start-Sleep -Seconds $IntervalSeconds
}
