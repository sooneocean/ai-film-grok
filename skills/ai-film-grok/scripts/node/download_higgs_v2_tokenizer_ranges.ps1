$ErrorActionPreference = 'Stop'

$root = 'C:\aifilm-audio-node'
$modelDir = Join-Path $root 'models\higgs-v2-tokenizer'
$target = Join-Path $modelDir 'model.safetensors'
$partsDir = Join-Path $modelDir '.model.safetensors.parts'
$expected = [int64]805665628
$chunkSize = [int64]67108864
$url = 'https://huggingface.co/bosonai/higgs-audio-v2-tokenizer/resolve/main/model.safetensors'

New-Item -ItemType Directory -Force -Path $modelDir, $partsDir | Out-Null

$offset = [int64]0
$index = 0
while ($offset -lt $expected) {
    $want = [Math]::Min($chunkSize, $expected - $offset)
    $end = $offset + $want - 1
    $part = Join-Path $partsDir ('{0:D3}.part' -f $index)
    if ((Test-Path -LiteralPath $part) -and (Get-Item -LiteralPath $part).Length -eq $want) {
        $offset += $want
        $index++
        continue
    }

    $partial = "$part.partial"
    $attempt = 0
    while ($true) {
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        & curl.exe -L --fail --connect-timeout 30 --speed-limit 1024 --speed-time 90 `
            --range "$offset-$end" -o $partial $url
        if ((Test-Path -LiteralPath $partial) -and (Get-Item -LiteralPath $partial).Length -eq $want) {
            break
        }
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        $attempt++
        if ($attempt -ge 100) { throw "Higgs tokenizer range $index did not produce its expected $want bytes" }
        Start-Sleep -Seconds 10
    }
    Move-Item -LiteralPath $partial -Destination $part -Force
    $offset += $want
    $index++
}

$assembled = "$target.assembling"
Remove-Item -LiteralPath $assembled -Force -ErrorAction SilentlyContinue
$out = [System.IO.File]::Open($assembled, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
try {
    $offset = [int64]0
    $index = 0
    while ($offset -lt $expected) {
        $want = [Math]::Min($chunkSize, $expected - $offset)
        $part = Join-Path $partsDir ('{0:D3}.part' -f $index)
        $input = [System.IO.File]::OpenRead($part)
        try { $input.CopyTo($out) } finally { $input.Dispose() }
        $offset += $want
        $index++
    }
} finally {
    $out.Dispose()
}
if ((Get-Item -LiteralPath $assembled).Length -ne $expected) {
    throw 'Higgs tokenizer assembled checkpoint size is invalid'
}
Move-Item -LiteralPath $assembled -Destination $target -Force
