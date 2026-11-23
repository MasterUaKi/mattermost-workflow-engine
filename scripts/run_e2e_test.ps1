# Author: Oleh Riabtsev
# File: scripts/run_e2e_test.ps1
# Created: 2026-11-23
# Version: 1.0.0

param(
    [string]$RepoPath = "C:\Entwiklung\mattermost-workflow-engine",
    [string]$MattermostUrl = "http://localhost:8065",
    [string]$EngineUrl = "http://localhost:8000",
    [ValidateSet("simple_expense_approval", "contract_approval_multistep")]
    [string]$WorkflowType = "contract_approval_multistep",
    [ValidateSet("en", "de")]
    [string]$DocLang = "en",
    [string]$ConsoleLang = ""
)

$ErrorActionPreference = "Stop"

function Get-DotEnvValue {
    param([string]$EnvPath, [string]$Key, [string]$DefaultValue = "")
    if (-not (Test-Path $EnvPath)) { return $DefaultValue }
    foreach ($Line in Get-Content -Path $EnvPath -Encoding UTF8) {
        if ($Line -match "^\s*${Key}\s*=\s*[`"']?([^`"'\r\n]+)[`"']?\s*$") {
            return $Matches[1].Trim()
        }
    }
    return $DefaultValue
}

$EnvFile = Join-Path $RepoPath ".env"
$BotToken = Get-DotEnvValue -EnvPath $EnvFile -Key "MATTERMOST_BOT_TOKEN"
if ([string]::IsNullOrWhiteSpace($BotToken) -or $BotToken -eq "replace_with_generated_bot_token") {
    throw "Valid MATTERMOST_BOT_TOKEN not found in $EnvFile. Run bootstrap_local_mattermost.ps1 first."
}

$SupportedConsoleLangs = @("en", "de", "ru")
$ActiveLang = if ($ConsoleLang -and ($SupportedConsoleLangs -contains $ConsoleLang.ToLower())) {
    $ConsoleLang.ToLower()
} else {
    $CfgLang = (Get-DotEnvValue -EnvPath $EnvFile -Key "CONSOLE_LANG" -DefaultValue "en").ToLower()
    if ($SupportedConsoleLangs -contains $CfgLang) { $CfgLang } else { "en" }
}

$Messages = @{
    en = @{
        fetching_users  = "Fetching Mattermost User IDs from {0}..."
        updating_yaml   = "Updating approver IDs in {0}..."
        restarting_app  = "Restarting workflow-engine container to reload workflows.yaml..."
        waiting_health  = "Waiting for workflow-engine health endpoint..."
        starting_wf     = "Submitting test workflow '{0}' (lang: {1})..."
        wf_created      = "Workflow started successfully! ID: {0} | Status: {1}"
        fetching_status = "Fetching full workflow state and audit trail..."
        next_hint       = "Open {0} in your browser and log in as '{1}' (password: TestUser2026!) to test Approve/Reject."
    }
    de = @{
        fetching_users  = "Rufe Mattermost User IDs von {0} ab..."
        updating_yaml   = "Aktualisiere Pr\u00fcfer-IDs in {0}..."
        restarting_app  = "Starte Container workflow-engine neu, um workflows.yaml neu zu laden..."
        waiting_health  = "Warte auf Health-Endpunkt von workflow-engine..."
        starting_wf     = "Starte Test-Prozess '{0}' (Sprache: {1})..."
        wf_created      = "Prozess erfolgreich gestartet! ID: {0} | Status: {1}"
        fetching_status = "Rufe aktuellen Prozessstatus und Audit-Historie ab..."
        next_hint       = "\u00d6ffnen Sie {0} im Browser und melden Sie sich als '{1}' (Passwort: TestUser2026!) an, um Genehmigen/Ablehnen zu testen."
    }
    ru = @{
        fetching_users  = "\u041f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u0435 Mattermost User ID \u0441 \u0441\u0435\u0440\u0432\u0435\u0440\u0430 {0}..."
        updating_yaml   = "\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 ID \u0441\u043e\u0433\u043b\u0430\u0441\u0443\u044e\u0449\u0438\u0445 \u0432 {0}..."
        restarting_app  = "\u041f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a \u043a\u043e\u043d\u0442\u0435\u0439\u043d\u0435\u0440\u0430 workflow-engine \u0434\u043b\u044f \u043f\u0435\u0440\u0435\u0447\u0438\u0442\u044b\u0432\u0430\u043d\u0438\u044f workflows.yaml..."
        waiting_health  = "\u041e\u0436\u0438\u0434\u0430\u043d\u0438\u0435 \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u0438 /health \u0441\u0435\u0440\u0432\u0438\u0441\u0430 workflow-engine..."
        starting_wf     = "\u041e\u0442\u043f\u0440\u0430\u0432\u043a\u0430 \u0442\u0435\u0441\u0442\u043e\u0432\u043e\u0433\u043e \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430 \u0432 \u043c\u0430\u0440\u0448\u0440\u0443\u0442 '{0}' (\u044f\u0437\u044b\u043a: {1})..."
        wf_created      = "\u041f\u0440\u043e\u0446\u0435\u0441\u0441 \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u0437\u0430\u043f\u0443\u0449\u0435\u043d! ID: {0} | \u0421\u0442\u0430\u0442\u0443\u0441: {1}"
        fetching_status = "\u041f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u0435 \u0442\u0435\u043a\u0443\u0449\u0435\u0433\u043e \u0441\u0442\u0430\u0442\u0443\u0441\u0430 \u0438 \u0438\u0441\u0442\u043e\u0440\u0438\u0438 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0439..."
        next_hint       = "\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 {0} \u0432 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0435 \u0438 \u0432\u043e\u0439\u0434\u0438\u0442\u0435 \u043f\u043e\u0434 '{1}' (\u043f\u0430\u0440\u043e\u043b\u044c: TestUser2026!), \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043a\u043d\u043e\u043f\u043a\u0438 Approve/Reject."
    }
}

function Get-Msg {
    param([string]$Key, [object[]]$FormatArgs = @())
    $Template = [regex]::Unescape($Messages[$ActiveLang][$Key])
    if ($FormatArgs.Count -gt 0) { return ($Template -f $FormatArgs) }
    return $Template
}

Write-Host (Get-Msg "fetching_users" @($MattermostUrl))
$Headers = @{ Authorization = "Bearer $BotToken" }

$Usernames = @("initiator_user", "teamlead_user", "dept_head_user", "legal_user", "finance_user", "ceo_user")
$UserIds = @{}
foreach ($Name in $Usernames) {
    $UserObj = Invoke-RestMethod -Uri "$MattermostUrl/api/v4/users/username/$Name" -Headers $Headers
    $UserIds[$Name] = $UserObj.id
}

$WorkflowsPath = Join-Path $RepoPath "workflows.yaml"
Write-Host (Get-Msg "updating_yaml" @($WorkflowsPath))

$YamlContent = Get-Content -Path $WorkflowsPath -Raw -Encoding UTF8
$YamlContent = $YamlContent -replace "mm_user_id_teamlead_01", $UserIds["teamlead_user"]
$YamlContent = $YamlContent -replace "mm_user_id_dept_head_01", $UserIds["dept_head_user"]
$YamlContent = $YamlContent -replace "mm_user_id_legal_01", $UserIds["legal_user"]
$YamlContent = $YamlContent -replace "mm_user_id_finance_01", $UserIds["finance_user"]
$YamlContent = $YamlContent -replace "mm_user_id_ceo_01", $UserIds["ceo_user"]

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($WorkflowsPath, $YamlContent, $Utf8NoBom)

Write-Host (Get-Msg "restarting_app")
Set-Location $RepoPath
docker compose restart workflow-engine | Out-Null

Write-Host (Get-Msg "waiting_health")
for ($i = 1; $i -le 15; $i++) {
    try {
        $Health = Invoke-RestMethod -Uri "$EngineUrl/health" -TimeoutSec 2
        if ($Health.status -eq "ok") { break }
    } catch {
        Start-Sleep -Seconds 1
    }
}

$TempDir = [System.IO.Path]::GetTempPath()
$SampleDocPath = Join-Path $TempDir "cloud_contract_2026_481.txt"
$MetaJsonPath = Join-Path $TempDir "workflow_meta_2026.json"

[System.IO.File]::WriteAllText(
    $SampleDocPath,
    "Sample Contract #2026-481`nVendor: Hetzner Online GmbH`nTotal Amount: 24500.00 EUR`nCost Center: IT-OPS",
    $Utf8NoBom
)
[System.IO.File]::WriteAllText(
    $MetaJsonPath,
    '{"amount": "24500.00 EUR", "vendor": "Hetzner Online GmbH", "cost_center": "IT-OPS"}',
    $Utf8NoBom
)

Write-Host (Get-Msg "starting_wf" @($WorkflowType, $DocLang))
$StartRaw = curl.exe -sS -X POST "$EngineUrl/api/v1/workflows/start" `
    -F "workflow_type=$WorkflowType" `
    -F "title=Cloud Infrastructure Contract #2026-481" `
    -F "description=Annual server hosting agreement for research cluster" `
    -F "initiator_id=$($UserIds['initiator_user'])" `
    -F "lang=$DocLang" `
    -F "document_data=<$MetaJsonPath" `
    -F "files=@$SampleDocPath;type=text/plain"

$StartResp = $StartRaw | ConvertFrom-Json
Write-Host (Get-Msg "wf_created" @($StartResp.workflow_id, $StartResp.status))

Write-Host (Get-Msg "fetching_status")
$Details = Invoke-RestMethod -Uri "$EngineUrl/api/v1/workflows/$($StartResp.workflow_id)"
$Details | ConvertTo-Json -Depth 6

$FirstApprover = if ($WorkflowType -eq "simple_expense_approval") { "teamlead_user" } else { "dept_head_user" }
Write-Host ""
Write-Host (Get-Msg "next_hint" @($MattermostUrl, $FirstApprover))
