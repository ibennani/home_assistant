# Inventera Home Assistant via REST API (Windows)
# Sparar rapport i reports\ (gitignorerad)

$ErrorActionPreference = "Stop"
$project_root = Split-Path -Parent $PSScriptRoot
$env_file = Join-Path $project_root ".env"

if (-not (Test-Path $env_file)) {
    Write-Error "Saknar .env — kopiera .env.example till .env och fyll i HA_URL och HA_TOKEN."
}

Get-Content $env_file | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        Set-Item -Path "env:$name" -Value $value
    }
}

if (-not $env:HA_URL -or -not $env:HA_TOKEN) {
    Write-Error "HA_URL och HA_TOKEN måste vara satta i .env"
}

$headers = @{
    Authorization = "Bearer $($env:HA_TOKEN)"
    "Content-Type" = "application/json"
}

Write-Host "Hämtar inventering från $($env:HA_URL) ..."

$config = Invoke-RestMethod -Uri "$($env:HA_URL)/api/config" -Headers $headers
$states = Invoke-RestMethod -Uri "$($env:HA_URL)/api/states" -Headers $headers

$addons = @()
try {
    $addon_resp = Invoke-RestMethod -Uri "$($env:HA_URL)/api/hassio/addons" -Headers $headers
    $addons = $addon_resp.data.addons | ForEach-Object { @{ name = $_.name; slug = $_.slug; state = $_.state; version = $_.version } }
} catch {
    Write-Host "Add-ons: ej tillgängliga (kräver HA OS/Supervisor)"
}

$entity_summary = $states | Group-Object { ($_.entity_id -split '\.')[0] } | ForEach-Object {
    @{ domain = $_.Name; count = $_.Count }
} | Sort-Object domain

$conversation = $states | Where-Object { $_.entity_id -like 'conversation.*' } | ForEach-Object {
    @{ entity_id = $_.entity_id; state = $_.state }
}

$report = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    homeassistant = @{
        version = $config.version
        location_name = $config.location_name
        time_zone = $config.time_zone
        components = @($config.components | Sort-Object)
    }
    entity_summary = $entity_summary
    conversation_agents = $conversation
    addons = $addons
}

$report_dir = Join-Path $project_root "reports"
New-Item -ItemType Directory -Force -Path $report_dir | Out-Null
$timestamp = Get-Date -Format "yyyyMMddTHHmmssZ"
$report_file = Join-Path $report_dir "inventory-$timestamp.json"

$report | ConvertTo-Json -Depth 10 | Set-Content -Path $report_file -Encoding UTF8

Write-Host ""
Write-Host "Klar: $report_file"
Write-Host "Version: $($config.version)"
Write-Host "Komponenter: $($config.components.Count)"
Write-Host "Tillägg: $($addons.Count)"

if ($config.components -contains "whatsapp") {
    Write-Host "WhatsApp: installerad"
} else {
    Write-Host "WhatsApp: saknas"
}
