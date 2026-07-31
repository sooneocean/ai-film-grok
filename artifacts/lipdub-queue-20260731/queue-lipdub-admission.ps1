$ErrorActionPreference = 'Stop'

$taskName = 'AiFilm-LipDub-22B-Admission'
$repo = 'Lightricks/LTX-2.3-22b-IC-LoRA-DubIt'
$weight = 'ltx-2.3-22b-ic-lora-lipdub-0.9.safetensors'
$root = 'C:\aifilm-model-staging\LTX-2.3-22b-IC-LoRA-DubIt'
$receiptDir = Join-Path $root 'receipts'
New-Item -ItemType Directory -Force -Path $receiptDir | Out-Null

$at = (Get-Date).ToUniversalTime().ToString('o')
$receipt = Join-Path $receiptDir ('admission-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '.json')

try {
    $queue = Invoke-RestMethod 'http://127.0.0.1:8188/queue' -TimeoutSec 8
    $running = @($queue.queue_running).Count
    $pending = @($queue.queue_pending).Count
    $gpuLine = (& nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits).Trim()
    $freeVramMiB = [int]$gpuLine
    $freeRamMiB = [int]((Get-Counter '\Memory\Available MBytes').CounterSamples[0].CookedValue)
    if ($running -ne 0 -or $pending -ne 0 -or $freeVramMiB -lt 24576 -or $freeRamMiB -lt 12288) {
        [pscustomobject]@{
            ok = $false; status = 'blocked_capacity'; at = $at; running = $running; pending = $pending
            free_vram_mib = $freeVramMiB; free_ram_mib = $freeRamMiB
            required_vram_mib = 24576; required_ram_mib = 12288
        } | ConvertTo-Json -Compress | Set-Content -Encoding utf8 $receipt
        exit 0
    }

    $downloadDir = Join-Path $root 'download'
    & hf download $repo $weight --local-dir $downloadDir --max-workers 1 --quiet
    if ($LASTEXITCODE -ne 0) { throw "hf download exited $LASTEXITCODE" }
    $file = Join-Path $downloadDir $weight
    if (-not (Test-Path -LiteralPath $file)) { throw 'downloaded LipDub weight is missing' }
    $sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant()
    [pscustomobject]@{
        ok = $true; status = 'staged'; at = $at; repo = $repo; weight = $weight
        path = $file; sha256 = $sha256; free_vram_mib = $freeVramMiB; free_ram_mib = $freeRamMiB
    } | ConvertTo-Json -Compress | Set-Content -Encoding utf8 $receipt
    schtasks /Delete /TN $taskName /F | Out-Null
} catch {
    [pscustomobject]@{
        ok = $false; status = 'blocked_or_failed'; at = $at; error = $_.Exception.Message
    } | ConvertTo-Json -Compress | Set-Content -Encoding utf8 $receipt
}
