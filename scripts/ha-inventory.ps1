# Inventera Home Assistant via REST API (Windows)
# Sparar rapport i reports\ (gitignorerad)

$ErrorActionPreference = "Stop"
$project_root = Split-Path -Parent $PSScriptRoot
$env_file = Join-Path $project_root ".env"

function Import-DotEnv {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Error "Saknar .env - kopiera .env.example till .env och fyll i HA_URL och HA_TOKEN."
    }

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $bytes = $bytes[3..($bytes.Length - 1)]
    }

    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    $text = $text -replace "`r`n", "`n" -replace "`r", "`n"

    foreach ($line in ($text -split "`n")) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            continue
        }

        $eq = $line.IndexOf('=')
        if ($eq -lt 1) {
            continue
        }

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
}

Import-DotEnv -Path $env_file

if (-not $env:HA_URL -or -not $env:HA_TOKEN) {
    Write-Error "HA_URL och HA_TOKEN maste vara satta i .env"
}

$headers = @{
    Authorization = "Bearer $($env:HA_TOKEN)"
    "Content-Type" = "application/json"
}

Write-Host "Hamtar inventering fran $($env:HA_URL) ..."

$config = Invoke-RestMethod -Uri "$($env:HA_URL)/api/config" -Headers $headers
$states = Invoke-RestMethod -Uri "$($env:HA_URL)/api/states" -Headers $headers

$addons = @()
try {
    $addon_resp = Invoke-RestMethod -Uri "$($env:HA_URL)/api/hassio/addons" -Headers $headers
    if ($addon_resp.data -and $addon_resp.data.addons) {
        $addons = $addon_resp.data.addons | ForEach-Object {
            @{ name = $_.name; slug = $_.slug; state = $_.state; version = $_.version }
        }
    }
} catch {
    Write-Host "Add-ons: ej tillgangliga (kraver HA OS/Supervisor eller hogre token-rattighet)"
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

$json = $report | ConvertTo-Json -Depth 10
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($report_file, $json, $utf8NoBom)

Write-Host ""
Write-Host "Klar: $report_file"
Write-Host "Version: $($config.version)"
Write-Host "Komponenter: $($config.components.Count)"
Write-Host "Tillagg: $($addons.Count)"

if ($config.components -contains "whatsapp") {
    Write-Host "WhatsApp: installerad"
} else {
    Write-Host "WhatsApp: saknas"
}
