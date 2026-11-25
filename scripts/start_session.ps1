# Author: Oleh Riabtsev
# File: scripts/start_session.ps1
# Created: 2026-11-25
# Version: 1.0.0

param(
    [string]$RepoPath = "C:\Entwiklung\mattermost-workflow-engine",
    [string]$EngineUrl = "http://localhost:8000",
    [int]$DockerWaitSeconds = 90,
    [switch]$SkipAutoSync
)

$ErrorActionPreference = "Stop"

function Test-DockerDaemon {
    docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-DockerRunning {
    param([int]$MaxWaitSeconds)

    if (Test-DockerDaemon) {
        Write-Host "[OK] Docker daemon is already running."
        return
    }

    Write-Host "[INFO] Docker daemon is not responding. Starting Docker Desktop..."
    $DesktopCandidates = @(
        "C:\Program Files\Docker\Docker\Docker Desktop.exe",
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe")
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

    if ($DesktopCandidates) {
        Start-Process -FilePath $DesktopCandidates
    } else {
        Start-Process "docker desktop" -ErrorAction SilentlyContinue
    }

    $Elapsed = 0
    while ($Elapsed -lt $MaxWaitSeconds) {
        Start-Sleep -Seconds 3
        $Elapsed += 3
        if (Test-DockerDaemon) {
            Write-Host "[OK] Docker daemon is ready (waited ${Elapsed}s)."
            return
        }
        Write-Host "[WAIT] Waiting for Docker engine... (${Elapsed}s / ${MaxWaitSeconds}s)"
    }

    throw "Docker daemon did not become ready within ${MaxWaitSeconds}s. Please check Docker Desktop / WSL2."
}

Set-Location -Path $RepoPath

Ensure-DockerRunning -MaxWaitSeconds $DockerWaitSeconds

Write-Host "[INFO] Starting Docker Compose services..."
docker compose up -d
docker compose ps

Write-Host "[INFO] Checking Workflow Engine health at $EngineUrl/health..."
$Healthy = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        $Health = Invoke-RestMethod -Uri "$EngineUrl/health" -TimeoutSec 3
        if ($Health.status -eq "ok") {
            $Healthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $Healthy) {
    docker compose logs --tail=30 workflow-engine
    throw "Workflow Engine did not respond with status 'ok' at $EngineUrl/health."
}

Write-Host "[OK] Workflow Engine is healthy ($EngineUrl/health -> status: ok)."

if (-not $SkipAutoSync) {
    $RegisterScript = Join-Path $RepoPath "scripts\register_autosync_task.ps1"
    if (Test-Path $RegisterScript) {
        powershell -ExecutionPolicy Bypass -File $RegisterScript
    }
}