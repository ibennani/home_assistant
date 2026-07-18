# Öppnar Home Assistant för att skapa long-lived access token
$project_root = Split-Path -Parent $PSScriptRoot
$env_file = Join-Path $project_root ".env"

$url = "http://192.168.0.222:8123"
if (Test-Path $env_file) {
    Get-Content $env_file | ForEach-Object {
        if ($_ -match '^\s*HA_URL=(.+)$') { $url = $matches[1].Trim() }
    }
}

$token_page = "$url/profile/security"
Write-Host "Öppnar: $token_page"
Write-Host ""
Write-Host "1. Klicka 'Create token' under Long-Lived Access Tokens"
Write-Host "2. Kopiera token till .env som HA_TOKEN=..."
Write-Host "3. Kör: .\scripts\ha-inventory.ps1"
Start-Process $token_page
