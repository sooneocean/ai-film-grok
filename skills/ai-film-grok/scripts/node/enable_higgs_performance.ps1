$ErrorActionPreference = 'Stop'

$root = 'C:\aifilm-audio-node'
$generation = Join-Path $root 'models\higgs-v2-generation\model.safetensors'
$tokenizer = Join-Path $root 'models\higgs-v2-tokenizer\model.safetensors'
$source = Join-Path $root 'higgs_performance.py.new'
$target = Join-Path $root 'higgs_performance.py'
$envPath = Join-Path $root 'node.env'
$generationBytes = [int64]11542613696
$tokenizerBytes = [int64]805665628

if (!(Test-Path -LiteralPath $generation) -or (Get-Item -LiteralPath $generation).Length -ne $generationBytes) {
    throw 'Higgs generation checkpoint is not complete'
}
if (!(Test-Path -LiteralPath $tokenizer) -or (Get-Item -LiteralPath $tokenizer).Length -ne $tokenizerBytes) {
    throw 'Higgs tokenizer checkpoint is not complete'
}
if (!(Test-Path -LiteralPath $source) -or !(Test-Path -LiteralPath $envPath)) {
    throw 'Higgs adapter source or node.env is unavailable'
}

$python = Join-Path $root 'third_party\higgs-audio\.venv\Scripts\python.exe'
$argv = @(
    $python, $target, '--prompt', '{prompt}', '--duration', '{duration}',
    '--seed', '{seed}', '--out', '{out}'
) | ConvertTo-Json -Compress
$updates = @{
    'HIGGS_PERFORMANCE_MODEL_PATH' = Split-Path -Parent $generation
    'HIGGS_PERFORMANCE_TOKENIZER_PATH' = Split-Path -Parent $tokenizer
    'AIFILM_AUDIO_NODE_PERFORMANCE_ARGV' = $argv
}
$lines = @(Get-Content -LiteralPath $envPath)
$seen = @{}
$output = foreach ($line in $lines) {
    $replacement = $null
    foreach ($key in $updates.Keys) {
        if ($line.StartsWith("$key=", [System.StringComparison]::Ordinal)) {
            $seen[$key] = $true
            $replacement = "$key=$($updates[$key])"
            break
        }
    }
    if ($null -ne $replacement) { $replacement } else { $line }
}
foreach ($key in $updates.Keys) {
    if (!$seen.ContainsKey($key)) { $output += "$key=$($updates[$key])" }
}

$adapterTemporary = "$target.next"
$envTemporary = "$envPath.next"
$adapterBackup = "$target.rollback"
$envBackup = "$envPath.rollback"
$adapterExisted = Test-Path -LiteralPath $target
$envBackedUp = $false
$adapterCommitted = $false
$envCommitted = $false
$cleanupBackups = $false

function Test-NodeHealth([bool]$requirePerformance) {
    $tokenLine = Get-Content -LiteralPath $envPath | Where-Object {
        $_.StartsWith('AIFILM_AUDIO_NODE_TOKEN=', [System.StringComparison]::Ordinal)
    } | Select-Object -First 1
    if (!$tokenLine) { return $false }
    $token = $tokenLine.Substring('AIFILM_AUDIO_NODE_TOKEN='.Length)
    $headers = @{ Authorization = "Bearer $token" }
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Headers $headers -Uri 'http://192.168.88.52:8788/health' -TimeoutSec 5
            if ($health.ok -eq $true -and (!$requirePerformance -or $health.models.performance -eq $true)) {
                return $true
            }
        } catch {}
        Start-Sleep -Seconds 2
    }
    return $false
}

function Restart-AudioNode {
    Stop-ScheduledTask -TaskName AiFilmAudioNode -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $listeners = @(Get-NetTCPConnection -LocalAddress '192.168.88.52' -LocalPort 8788 -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction Stop
        if ($process.Name -ne 'python.exe' -or $process.CommandLine -notmatch 'audio_node_service:app') {
            throw "refusing to stop unexpected listener on 192.168.88.52:8788 (pid $($listener.OwningProcess))"
        }
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
    }
    Start-Sleep -Seconds 2
    Start-ScheduledTask -TaskName AiFilmAudioNode
}

try {
    Copy-Item -LiteralPath $source -Destination $adapterTemporary -Force
    [System.IO.File]::WriteAllLines($envTemporary, [string[]]$output)
    if ($adapterExisted) { Copy-Item -LiteralPath $target -Destination $adapterBackup -Force }
    Copy-Item -LiteralPath $envPath -Destination $envBackup -Force
    $envBackedUp = $true
    Move-Item -LiteralPath $adapterTemporary -Destination $target -Force
    $adapterCommitted = $true
    Move-Item -LiteralPath $envTemporary -Destination $envPath -Force
    $envCommitted = $true
    Restart-AudioNode
    if (!(Test-NodeHealth $true)) { throw 'audio node did not report Higgs performance readiness' }
    $cleanupBackups = $true
} catch {
    $restored = $true
    try {
        if ($adapterCommitted) {
            if ($adapterExisted -and (Test-Path -LiteralPath $adapterBackup)) {
                Move-Item -LiteralPath $adapterBackup -Destination $target -Force
            } elseif (!$adapterExisted) {
                Remove-Item -LiteralPath $target -Force -ErrorAction Stop
            } else {
                throw 'adapter backup is unavailable'
            }
        }
        if ($envCommitted) {
            if (!$envBackedUp -or !(Test-Path -LiteralPath $envBackup)) {
                throw 'node environment backup is unavailable'
            }
            Move-Item -LiteralPath $envBackup -Destination $envPath -Force
        }
        if ($adapterCommitted -or $envCommitted) {
            Restart-AudioNode
            if (!(Test-NodeHealth $false)) { throw 'prior node health did not recover' }
        }
    } catch {
        $restored = $false
    }
    if (!$restored) {
        throw 'Higgs performance enablement failed and rollback backups were retained'
    }
    $cleanupBackups = $true
    throw 'Higgs performance enablement failed; prior node configuration was restored'
} finally {
    $sensitivePaths = @($adapterTemporary, $envTemporary)
    if ($cleanupBackups) { $sensitivePaths += @($adapterBackup, $envBackup) }
    foreach ($path in $sensitivePaths) {
        if (Test-Path -LiteralPath $path) {
            try {
                Remove-Item -LiteralPath $path -Force -ErrorAction Stop
            } catch {
                throw 'sensitive Higgs node temporary files could not be removed'
            }
        }
    }
}
