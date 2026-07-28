$ErrorActionPreference = 'Stop'

$root = 'C:\aifilm-audio-node'
$modelDir = Join-Path $root 'models\higgs-v2-generation'
$target = Join-Path $modelDir 'model.safetensors'
$partsDir = Join-Path $modelDir '.model.safetensors.parts'
$expected = [int64]11542613696
$firstChunkSize = [int64]536870912
$chunkSize = [int64]67108864
$url = 'https://huggingface.co/bosonai/higgs-audio-v2-generation-3B-base/resolve/main/model.safetensors'

New-Item -ItemType Directory -Force -Path $modelDir, $partsDir | Out-Null

$offset = [int64]0
$index = 0
while ($offset -lt $expected) {
    $size = if ($offset -eq 0) { $firstChunkSize } else { $chunkSize }
    $end = [Math]::Min($offset + $size - 1, $expected - 1)
    $want = $end - $offset + 1
    $part = Join-Path $partsDir ('{0:D3}.part' -f $index)
    if ((Test-Path -LiteralPath $part) -and (Get-Item -LiteralPath $part).Length -eq $want) {
        $offset += $want
        $index++
        continue
    }

    $partial = "$part.partial"
    $attempt = 0
    while ($true) {
        # Hugging Face redirect endpoints can ignore an append resume range.
        # A verified standalone segment never promotes a duplicated response.
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        & curl.exe -L --fail --connect-timeout 30 --speed-limit 1024 --speed-time 90 `
            --range "$offset-$end" -o $partial $url
        if ((Test-Path -LiteralPath $partial) -and (Get-Item -LiteralPath $partial).Length -eq $want) {
            break
        }
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        $attempt++
        if ($attempt -ge 100) { throw "Higgs range $index did not produce its expected $want bytes" }
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
        $size = if ($offset -eq 0) { $firstChunkSize } else { $chunkSize }
        $want = [Math]::Min($size, $expected - $offset)
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
    throw 'Higgs assembled checkpoint size is invalid'
}
Move-Item -LiteralPath $assembled -Destination $target -Force
