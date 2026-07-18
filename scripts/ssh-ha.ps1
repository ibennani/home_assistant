# SSH till Home Assistant med MAC-algoritm som fungerar mot HA OS (Windows-fix)
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemoteCommand
)

$project_root = Split-Path -Parent $PSScriptRoot
$env_file = Join-Path $project_root ".env"
$host_addr = "192.168.0.222"
$user = "root"
$port = 22

if (Test-Path $env_file) {
    Get-Content $env_file | ForEach-Object {
        if ($_ -match '^\s*HA_SSH_HOST=(.+)$') { $host_addr = $matches[1].Trim() }
        if ($_ -match '^\s*HA_SSH_USER=(.+)$') { $user = $matches[1].Trim() }
        if ($_ -match '^\s*HA_SSH_PORT=(.+)$') { $port = $matches[1].Trim() }
    }
}

$ssh_args = @(
    "-4",
    "-p", $port,
    "-o", "ConnectTimeout=10",
    "-o", "MACs=hmac-sha2-256-etm@openssh.com,hmac-sha2-256",
    "${user}@${host_addr}"
)

if ($RemoteCommand.Count -gt 0) {
    & ssh @ssh_args ($RemoteCommand -join " ")
} else {
    & ssh @ssh_args
}
