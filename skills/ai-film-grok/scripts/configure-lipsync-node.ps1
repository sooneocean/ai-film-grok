param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[0-9a-f]{64}$")]
    [string]$LatentSyncCheckpointSha256,
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[0-9a-f]{40}$")]
    [string]$LatentSyncRepoCommit
)

$ErrorActionPreference = "Stop"
$NodeRoot = "C:\aifilm-lipsync-node"
$Template = Join-Path $NodeRoot "node.env.example"
$EnvironmentFile = Join-Path $NodeRoot "node.env"

if (-not (Test-Path $Template)) {
    throw "Missing $Template"
}

$TokenBytes = New-Object byte[] 32
$Generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $Generator.GetBytes($TokenBytes)
}
finally {
    $Generator.Dispose()
}
$Token = ([BitConverter]::ToString($TokenBytes)).Replace("-", "").ToLowerInvariant()
$Content = Get-Content $Template -Raw
$Content = $Content.Replace(
    "CHANGE_ME_MINIMUM_32_RANDOM_CHARACTERS",
    $Token
)
$Content = $Content.Replace(
    "AIFILM_LIPSYNC_NODE_LATENTSYNC_CHECKPOINT_SHA256=CHANGE_ME",
    "AIFILM_LIPSYNC_NODE_LATENTSYNC_CHECKPOINT_SHA256=$LatentSyncCheckpointSha256"
)
$Content = $Content.Replace(
    "AIFILM_LIPSYNC_NODE_LATENTSYNC_REPO_COMMIT=CHANGE_ME",
    "AIFILM_LIPSYNC_NODE_LATENTSYNC_REPO_COMMIT=$LatentSyncRepoCommit"
)
[IO.File]::WriteAllText($EnvironmentFile, $Content, [Text.UTF8Encoding]::new($false))

& icacls $EnvironmentFile /inheritance:r /grant:r "${env:USERNAME}:(F)" | Out-Null

$TaskName = "AI Film LipSync Node"
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\aifilm-lipsync-node\start-lipsync-node.ps1"
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Description "Loopback-only RTX lip-sync inference gateway" `
    -Force | Out-Null

Write-Output "configured"
