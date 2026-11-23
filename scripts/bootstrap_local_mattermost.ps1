# Author: Oleh Riabtsev
# File: scripts/bootstrap_local_mattermost.ps1
# Created: 2026-11-23
# Version: 1.0.1

param(
    [string]$RepoPath = "C:\Entwiklung\mattermost-workflow-engine",
    [string]$MattermostUrl = "http://localhost:8065",
    [string]$AdminUser = "mm_admin",
    [string]$AdminEmail = "admin@local.test",
    [string]$AdminPassword = "AdminPass2026!",
    [string]$TeamName = "approval-lab",
    [string]$ConsoleLang = ""
)

$ErrorActionPreference = "Stop"

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

$Messages = @{
    en = @{
        wait_mm         = "Waiting for local Mattermost server at {0}..."
        mm_ready        = "Mattermost API is online."
        creating_admin  = "Creating or logging in initial system admin '{0}'..."
        creating_team   = "Ensuring test team '{0}' exists..."
        creating_users  = "Creating test approver accounts (password for all test users: {0})..."
        creating_bot    = "Creating bot account 'approval-bot' and generating access token..."
        env_updated     = "Updated MATTERMOST_BOT_TOKEN in {0}."
        summary_header  = "Bootstrap completed. Mattermost User IDs:"
    }
    de = @{
        wait_mm         = "Warte auf lokalen Mattermost-Server unter {0}..."
        mm_ready        = "Mattermost API ist erreichbar."
        creating_admin  = "Erstelle oder melde Systemadministrator '{0}' an..."
        creating_team   = "Pr\u00fcfe Test-Team '{0}'..."
        creating_users  = "Erstelle Test-Pr\u00fcferkonten (Passwort f\u00fcr alle Testbenutzer: {0})..."
        creating_bot    = "Erstelle Bot-Konto 'approval-bot' und generiere Zugriffstoken..."
        env_updated     = "MATTERMOST_BOT_TOKEN in {0} aktualisiert."
        summary_header  = "Initialisierung abgeschlossen. Mattermost User IDs:"
    }
    ru = @{
        wait_mm         = "\u041e\u0436\u0438\u0434\u0430\u043d\u0438\u0435 \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u0438 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0441\u0435\u0440\u0432\u0435\u0440\u0430 Mattermost ({0})..."
        mm_ready        = "Mattermost API \u0433\u043e\u0442\u043e\u0432 \u043a \u0440\u0430\u0431\u043e\u0442\u0435."
        creating_admin  = "\u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435 \u0438\u043b\u0438 \u0432\u0445\u043e\u0434 \u043f\u043e\u0434 \u0441\u0438\u0441\u0442\u0435\u043c\u043d\u044b\u043c \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u043e\u043c '{0}'..."
        creating_team   = "\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0442\u0435\u0441\u0442\u043e\u0432\u043e\u0439 \u043a\u043e\u043c\u0430\u043d\u0434\u044b '{0}'..."
        creating_users  = "\u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435 \u0442\u0435\u0441\u0442\u043e\u0432\u044b\u0445 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439 (\u043f\u0430\u0440\u043e\u043b\u044c \u0434\u043b\u044f \u0432\u0441\u0435\u0445: {0})..."
        creating_bot    = "\u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435 \u0431\u043e\u0442\u0430 'approval-bot' \u0438 \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044f \u0442\u043e\u043a\u0435\u043d\u0430..."
        env_updated     = "\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440 MATTERMOST_BOT_TOKEN \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d \u0432 {0}."
        summary_header  = "\u0418\u043d\u0438\u0446\u0438\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430. Mattermost User ID:"
    }
}

function Get-Msg {
    param([string]$Key, [object[]]$FormatArgs = @())
    $Template = [regex]::Unescape($Messages[$ActiveLang][$Key])
    if ($FormatArgs.Count -gt 0) { return ($Template -f $FormatArgs) }
    return $Template
}

# 1. Wait until Mattermost HTTP ping responds
Write-Host (Get-Msg "wait_mm" @($MattermostUrl))
$MaxRetries = 30
for ($i = 1; $i -le $MaxRetries; $i++) {
    try {
        $Ping = Invoke-RestMethod -Uri "$MattermostUrl/api/v4/system/ping" -TimeoutSec 3
        if ($Ping.status -eq "OK") {
            Write-Host (Get-Msg "mm_ready")
            break
        }
    } catch {
        if ($i -eq $MaxRetries) { throw "Mattermost did not become ready in time at $MattermostUrl" }
        Start-Sleep -Seconds 2
    }
}

# 2. Register first user (automatically becomes system_admin) if not already registered
Write-Host (Get-Msg "creating_admin" @($AdminUser))
try {
    $CreateAdminBody = @{
        email      = $AdminEmail
        username   = $AdminUser
        password   = $AdminPassword
        first_name = "System"
        last_name  = "Admin"
    } | ConvertTo-Json
    Invoke-RestMethod -Uri "$MattermostUrl/api/v4/users" -Method POST -Body $CreateAdminBody -ContentType "application/json" | Out-Null
} catch {
    # Admin already exists
}

$LoginBody = @{ login_id = $AdminUser; password = $AdminPassword } | ConvertTo-Json
$LoginResp = Invoke-WebRequest -Uri "$MattermostUrl/api/v4/users/login" -Method POST -Body $LoginBody -ContentType "application/json"
$SessionToken = $LoginResp.Headers["Token"]
if ($SessionToken -is [array]) { $SessionToken = $SessionToken[0] }
$Headers = @{ Authorization = "Bearer $SessionToken"; "Content-Type" = "application/json" }

# 3. Create or fetch test team
Write-Host (Get-Msg "creating_team" @($TeamName))
try {
    $Team = Invoke-RestMethod -Uri "$MattermostUrl/api/v4/teams/name/$TeamName" -Headers $Headers
} catch {
    $TeamBody = @{ name = $TeamName; display_name = "Approval Lab"; type = "O" } | ConvertTo-Json
    $Team = Invoke-RestMethod -Uri "$MattermostUrl/api/v4/teams" -Method POST -Headers $Headers -Body $TeamBody
}

# 4. Create sample test users for workflow roles
$TestUserPass = "TestUser2026!"
Write-Host (Get-Msg "creating_users" @($TestUserPass))

$TestAccounts = @(
    @{ username = "initiator_user"; first_name = "Alex";   last_name = "Initiator" },
    @{ username = "teamlead_user";  first_name = "Sarah";  last_name = "TeamLead" },
    @{ username = "dept_head_user"; first_name = "Markus"; last_name = "DeptHead" },
    @{ username = "legal_user";     first_name = "Elena";  last_name = "Legal" },
    @{ username = "finance_user";   first_name = "Thomas"; last_name = "Finance" },
    @{ username = "ceo_user";       first_name = "Oliver"; last_name = "Executive" }
)

$UserTable = @()
foreach ($Acc in $TestAccounts) {
    try {
        $UserObj = Invoke-RestMethod -Uri "$MattermostUrl/api/v4/users/username/$($Acc.username)" -Headers $Headers
    } catch {
        $UserPayload = @{
            email      = "$($Acc.username)@local.test"
            username   = $Acc.username
            password   = $TestUserPass
            first_name = $Acc.first_name
            last_name  = $Acc.last_name
        } | ConvertTo-Json
        $UserObj = Invoke-RestMethod -Uri "$MattermostUrl/api/v4/users" -Method POST -Headers $Headers -Body $UserPayload
    }

    try {
        $MemberBody = @{ team_id = $Team.id; user_id = $UserObj.id } | ConvertTo-Json
        Invoke-RestMethod -Uri "$MattermostUrl/api/v4/teams/$($Team.id)/members" -Method POST -Headers $Headers -Body $MemberBody | Out-Null
    } catch {}

    $UserTable += [PSCustomObject]@{
        RoleUsername = $Acc.username
        UserId       = $UserObj.id
        Password     = $TestUserPass
    }
}

# 5. Create bot account and access token
Write-Host (Get-Msg "creating_bot")
$Bots = Invoke-RestMethod -Uri "$MattermostUrl/api/v4/bots?include_deleted=false" -Headers $Headers
$Bot = $Bots | Where-Object { $_.username -eq "approval-bot" } | Select-Object -First 1

if (-not $Bot) {
    $BotPayload = @{
        username     = "approval-bot"
        display_name = "Document Approval Bot"
        description  = "Automated Document Approval Workflow Engine"
    } | ConvertTo-Json
    $Bot = Invoke-RestMethod -Uri "$MattermostUrl/api/v4/bots" -Method POST -Headers $Headers -Body $BotPayload
}

try {
    $BotMemberBody = @{ team_id = $Team.id; user_id = $Bot.user_id } | ConvertTo-Json
    Invoke-RestMethod -Uri "$MattermostUrl/api/v4/teams/$($Team.id)/members" -Method POST -Headers $Headers -Body $BotMemberBody | Out-Null
} catch {}

$TokenPayload = @{ description = "Workflow Engine Token $(Get-Date -Format 'yyyyMMdd-HHmmss')" } | ConvertTo-Json
$TokenResp = Invoke-RestMethod -Uri "$MattermostUrl/api/v4/users/$($Bot.user_id)/tokens" -Method POST -Headers $Headers -Body $TokenPayload
$BotToken = $TokenResp.token

# 6. Update .env (UTF-8 without BOM) with the generated token
$EnvPath = Join-Path $RepoPath ".env"
if (-not (Test-Path $EnvPath)) {
    Copy-Item (Join-Path $RepoPath ".env.example") $EnvPath
}

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$EnvRaw = [System.IO.File]::ReadAllText($EnvPath, [System.Text.Encoding]::UTF8)
if ($EnvRaw -match '(?m)^MATTERMOST_BOT_TOKEN=.*$') {
    $EnvRaw = [regex]::Replace($EnvRaw, '(?m)^MATTERMOST_BOT_TOKEN=.*$', "MATTERMOST_BOT_TOKEN=`"$BotToken`"")
} else {
    $EnvRaw = $EnvRaw.TrimEnd() + "`r`nMATTERMOST_BOT_TOKEN=`"$BotToken`"`r`n"
}
[System.IO.File]::WriteAllText($EnvPath, $EnvRaw, $Utf8NoBom)

Write-Host (Get-Msg "env_updated" @($EnvPath))
Write-Host ""
Write-Host (Get-Msg "summary_header")
$UserTable | Format-Table -AutoSize