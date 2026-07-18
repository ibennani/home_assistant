# Verifiera Home Assistant MCP-anslutning (LAN, Nabu webhook, REST API)
# Kör från projektroten: .\scripts\verify-ha-mcp.ps1

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env"
$globalMcp = Join-Path $env:USERPROFILE ".cursor\mcp.json"
$projectMcp = Join-Path $projectRoot ".cursor\mcp.json"
$lanHost = "192.168.0.222"
$lanPort = 9583

function Import-DotEnv {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $bytes = $bytes[3..($bytes.Length - 1)]
    }

    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    $text = $text -replace "`r`n", "`n" -replace "`r", "`n"

    foreach ($line in ($text -split "`n")) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }

        $eq = $line.IndexOf('=')
        if ($eq -lt 1) { continue }

        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim()

        if (($value.Length -ge 2) -and (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))
            )) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        Set-Item -Path "env:$name" -Value $value -Force
    }

    return $true
}

function Get-HttpStatus {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [hashtable]$Headers = @{},
        [int]$TimeoutSec = 15
    )

    try {
        $params = @{
            Uri             = $Uri
            Method          = 'GET'
            UseBasicParsing = $true
            TimeoutSec      = $TimeoutSec
        }
        if ($Headers.Count -gt 0) {
            $params.Headers = $Headers
        }
        $response = Invoke-WebRequest @params
        return [int]$response.StatusCode
    }
    catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode.value__
        }
        throw
    }
}

function Get-McpWebhookUrl {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $json = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if (-not $json.mcpServers) {
        return $null
    }

    $server = $json.mcpServers.'home-assistant'
    if (-not $server) {
        return $null
    }

    return [string]$server.url
}

function Mask-Url {
    param([string]$Url)

    if (-not $Url) { return "(saknas)" }
    return ($Url -replace '/mcp_[a-f0-9]+$', '/mcp_****')
}

function Test-Expectation {
    param(
        [string]$Name,
        [int]$Status,
        [int[]]$Expected,
        [string]$Detail = ""
    )

    $ok = $Expected -contains $Status
    $icon = if ($ok) { "OK" } else { "FAIL" }
    $expectedText = ($Expected | ForEach-Object { "$_" }) -join " eller "
    $suffix = if ($Detail) { " - $Detail" } else { "" }
    Write-Host ("[{0}] {1}: HTTP {2} (forvantat {3}){4}" -f $icon, $Name, $Status, $expectedText, $suffix)
    return $ok
}

Write-Host "=== Home Assistant MCP-verifiering ===" -ForegroundColor Cyan
Write-Host ""

$results = @()

# mcp.json
$globalUrl = Get-McpWebhookUrl -Path $globalMcp
$projectUrl = Get-McpWebhookUrl -Path $projectMcp

Write-Host "MCP-konfiguration:"
Write-Host ("  Global:  {0}" -f (Mask-Url $globalUrl))
Write-Host ("  Projekt: {0}" -f (Mask-Url $projectUrl))

if ($globalUrl -and $projectUrl -and ($globalUrl -eq $projectUrl)) {
    Write-Host "  [OK] Global och projekt-mcp.json har samma home-assistant-URL"
    $results += $true
}
elseif ($globalUrl -or $projectUrl) {
    Write-Host "  [FAIL] URL:erna matchar inte (eller en fil saknar home-assistant)"
    $results += $false
}
else {
    Write-Host "  [FAIL] Ingen home-assistant-post hittades i mcp.json"
    $results += $false
}

if ($globalUrl -and ($globalUrl -notmatch '^https://.+\.ui\.nabu\.casa/api/webhook/mcp_[a-f0-9]+$')) {
    Write-Host "  [WARN] Global URL foljer inte forvantat Nabu-webhook-format"
}

Write-Host ""

# LAN MCP add-on
$lanRoot = "http://${lanHost}:${lanPort}/"
$lanStatus = Get-HttpStatus -Uri $lanRoot -TimeoutSec 10
$results += (Test-Expectation -Name "LAN MCP add-on (rot)" -Status $lanStatus -Expected @(403) -Detail $lanRoot)

# Nabu webhook
if ($globalUrl) {
    $webhookStatus = Get-HttpStatus -Uri $globalUrl -TimeoutSec 20
    $results += (Test-Expectation -Name "Nabu Casa webhook" -Status $webhookStatus -Expected @(405) -Detail (Mask-Url $globalUrl))
}
else {
    Write-Host "[SKIP] Nabu webhook - ingen URL i mcp.json"
    $results += $false
}

# HA REST API
if (Import-DotEnv -Path $envFile) {
    if ($env:HA_URL -and $env:HA_TOKEN) {
        $headers = @{ Authorization = "Bearer $($env:HA_TOKEN)" }
        $apiStatus = Get-HttpStatus -Uri "$($env:HA_URL)/api/" -Headers $headers -TimeoutSec 15
        $results += (Test-Expectation -Name "HA REST API" -Status $apiStatus -Expected @(200) -Detail $env:HA_URL)
    }
    else {
        Write-Host "[SKIP] HA REST API - HA_URL eller HA_TOKEN saknas i .env"
        $results += $false
    }
}
else {
    Write-Host "[SKIP] HA REST API - .env saknas (kopiera .env.example)"
    $results += $false
}

Write-Host ""
$passed = @($results | Where-Object { $_ }).Count
$total = $results.Count

if ($passed -eq $total) {
    Write-Host "=== Alla $total kontroller OK ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Lokal Agent-chatt ska fungera. För Cursor Automation (cursor+ha test):"
    Write-Host "  Lägg till samma MCP-server på https://cursor.com/settings (namn: home-assistant)"
    Write-Host "  Se docs/cursor-cloud-mcp-steg.md"
    exit 0
}

Write-Host "=== $passed/$total kontroller OK ===" -ForegroundColor Yellow
exit 1
