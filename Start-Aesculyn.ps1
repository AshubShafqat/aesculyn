param(
    [string]$DatasetPath,
    [int]$Port = 8780
)
$ErrorActionPreference = 'Stop'
if ($DatasetPath) {
    $resolvedDataset = (Resolve-Path -LiteralPath $DatasetPath).Path
    if (-not $resolvedDataset.EndsWith('.zip', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'DatasetPath must point to the authorized dataset ZIP.'
    }
    $env:AESCULYN_DATASET = $resolvedDataset
    $env:AESCULYN_ENABLE_TRAINING = '1'
} else {
    $env:AESCULYN_ENABLE_TRAINING = '0'
}
$env:AESCULYN_HOST = '127.0.0.1'
$env:PORT = [string]$Port
Write-Host "Aesculyn opens at http://127.0.0.1:$Port"
if ($DatasetPath) { Write-Host 'Local model training is enabled for this process.' }
python app.py
