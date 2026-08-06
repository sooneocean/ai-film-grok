param(
    [string]$Root = 'C:\aifilm-comfy-broker',
    [int]$Port = 8189
)

$ErrorActionPreference = 'Stop'
$envFile = Join-Path $Root 'node.env'
$service = Join-Path $Root 'comfy_broker_service.py'
$python = 'C:\aifilm-lipsync-node\venv\Scripts\python.exe'
if (-not (Test-Path $envFile) -or -not (Test-Path $service) -or -not (Test-Path $python)) {
    throw 'Broker files or the approved Python runtime are missing'
}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^([A-Z0-9_]+)=(.+)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
if ($env:AIFILM_COMFY_BROKER_TOKEN.Length -lt 32) { throw 'Broker token is invalid' }
if ($env:AIFILM_COMFY_BROKER_WEAPON_IDS.Length -lt 3) { throw 'Broker weapon allowlist is missing' }

Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like '*comfy_broker_service*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$stdout = Join-Path $Root 'broker.stdout.log'
$stderr = Join-Path $Root 'broker.stderr.log'
Start-Process -FilePath $python -ArgumentList '-m','uvicorn','comfy_broker_service:app','--host','127.0.0.1','--port',$Port `
    -WorkingDirectory $Root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden
Start-Sleep -Seconds 2
if (-not (Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort $Port -ErrorAction SilentlyContinue)) {
    throw 'Broker did not bind to loopback'
}
Write-Output 'AIFILM_COMFY_BROKER_READY'
