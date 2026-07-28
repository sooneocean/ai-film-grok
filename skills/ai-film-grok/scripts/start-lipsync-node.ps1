$ErrorActionPreference = "Stop"

$NodeRoot = "C:\aifilm-lipsync-node"
$EnvironmentFile = Join-Path $NodeRoot "node.env"
$Python = Join-Path $NodeRoot "venv\Scripts\python.exe"
$Service = Join-Path $NodeRoot "lipsync_node_service.py"

if (-not (Test-Path $EnvironmentFile)) {
    throw "Missing $EnvironmentFile"
}
if (-not (Test-Path $Python) -or -not (Test-Path $Service)) {
    throw "Lip-sync node runtime is incomplete"
}

Get-Content $EnvironmentFile | ForEach-Object {
    $Line = $_.Trim()
    if ($Line -and -not $Line.StartsWith("#") -and $Line.Contains("=")) {
        $Name, $Value = $Line.Split("=", 2)
        $Name = $Name.Trim()
        if (-not $Name.StartsWith("AIFILM_LIPSYNC_NODE_")) {
            throw "Unsupported environment key: $Name"
        }
        [Environment]::SetEnvironmentVariable($Name, $Value.Trim(), "Process")
    }
}

$Token = [Environment]::GetEnvironmentVariable("AIFILM_LIPSYNC_NODE_TOKEN", "Process")
if ($Token -notmatch "^[0-9a-f]{64}$") {
    throw "AIFILM_LIPSYNC_NODE_TOKEN must be a random 256-bit lowercase hex token"
}

& $Python $Service
exit $LASTEXITCODE
