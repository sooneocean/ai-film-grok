$ErrorActionPreference = 'Stop'
$root = 'C:\aifilm-audio-node'
$envFile = Join-Path $root 'node.env'

Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#;=\s]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}

$env:HF_HUB_CACHE = 'C:\AI_Models\hf-cache'
$env:HF_HUB_OFFLINE = '1'
$toolExecutables = @(
    $env:AIFILM_AUDIO_NODE_FFMPEG,
    $env:AIFILM_AUDIO_NODE_SOX
) | Where-Object { $_ }
foreach ($executable in $toolExecutables) {
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "configured audio-node executable is missing: $executable"
    }
    $toolDirectory = Split-Path -Parent $executable
    if (($env:PATH -split ';') -notcontains $toolDirectory) {
        $env:PATH = "$toolDirectory;$env:PATH"
    }
}
$bindHost = if ($env:AIFILM_AUDIO_NODE_BIND_HOST) {
    $env:AIFILM_AUDIO_NODE_BIND_HOST
} else {
    '127.0.0.1'
}

if ($bindHost -ne '127.0.0.1') {
    throw 'audio node must bind to loopback and be reached through an SSH tunnel'
}

Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like '*audio_node_service:app*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Process `
    -FilePath (Join-Path $root 'venv-clean\Scripts\python.exe') `
    -ArgumentList @('-m', 'uvicorn', 'audio_node_service:app', '--host', $bindHost, '--port', '8788') `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $root 'service-scheduled.out.log') `
    -RedirectStandardError (Join-Path $root 'service-scheduled.err.log')
