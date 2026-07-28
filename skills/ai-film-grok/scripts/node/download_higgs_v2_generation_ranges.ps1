$ErrorActionPreference = 'Stop'

$root = 'C:\aifilm-audio-node'
$modelDir = Join-Path $root 'models\higgs-v2-generation'
$target = Join-Path $modelDir 'model.safetensors'
$partsDir = Join-Path $modelDir '.model.safetensors.parts'
$expected = [int64]11542613696
$chunkSize = [int64]536870912
$url = 'https://huggingface.co/bosonai/higgs-audio-v2-generation-3B-base/resolve/main/model.safetensors'

New-Item -ItemType Directory -Force -Path $modelDir, $partsDir | Out-Null

for ($offset = [int64]0; $offset -lt $expected; $offset += $chunkSize) {
    $end = [Math]::Min($offset + $chunkSize - 1, $expected - 1)
    $want = $end - $offset + 1
    $index = [int]($offset / $chunkSize)
    $part = Join-Path $partsDir ('{0:D3}.part' -f $index)
    if ((Test-Path -LiteralPath $part) -and (Get-Item -LiteralPath $part).Length -eq $want) {
        continue
    }

    $partial = "$part.partial"
    $attempt = 0
    while ($true) {
        $have = if (Test-Path -LiteralPath $partial) { (Get-Item -LiteralPath $partial).Length } else { [int64]0 }
        if ($have -gt $want) {
            Remove-Item -LiteralPath $partial -Force
            $have = [int64]0
        }
        $rangeStart = $offset + $have
        if ($have -gt 0) {
            & curl.exe -L --fail --connect-timeout 30 --speed-limit 1024 --speed-time 90 `
                --range "$rangeStart-$end" --append -o $partial $url
        } else {
            & curl.exe -L --fail --connect-timeout 30 --speed-limit 1024 --speed-time 90 `
                --range "$rangeStart-$end" -o $partial $url
        }
        if ((Test-Path -LiteralPath $partial) -and (Get-Item -LiteralPath $partial).Length -eq $want) {
            break
        }
        $attempt++
        if ($attempt -ge 100) { throw "Higgs range $index did not produce its expected $want bytes" }
        Start-Sleep -Seconds 10
    }
    Move-Item -LiteralPath $partial -Destination $part -Force
}

$assembled = "$target.assembling"
Remove-Item -LiteralPath $assembled -Force -ErrorAction SilentlyContinue
$out = [System.IO.File]::Open($assembled, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
try {
    for ($index = 0; $index -lt [Math]::Ceiling($expected / $chunkSize); $index++) {
        $part = Join-Path $partsDir ('{0:D3}.part' -f $index)
        $input = [System.IO.File]::OpenRead($part)
        try { $input.CopyTo($out) } finally { $input.Dispose() }
    }
} finally {
    $out.Dispose()
}
if ((Get-Item -LiteralPath $assembled).Length -ne $expected) {
    throw 'Higgs assembled checkpoint size is invalid'
}
Move-Item -LiteralPath $assembled -Destination $target -Force
