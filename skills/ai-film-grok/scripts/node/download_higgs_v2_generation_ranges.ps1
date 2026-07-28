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
    Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
    & curl.exe -L --fail --retry 100 --retry-all-errors --retry-delay 10 --connect-timeout 30 `
        --speed-limit 1024 --speed-time 90 `
        --range "$offset-$end" -o $partial $url
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $partial) -or (Get-Item -LiteralPath $partial).Length -ne $want) {
        throw "Higgs range $index did not produce its expected $want bytes"
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
