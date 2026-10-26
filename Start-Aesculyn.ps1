param(
    [string]$DatasetPath,
    [int]$Port = 8780,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
Set-Location -LiteralPath $project

$pythonCommand = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 --version *> $null
    if ($LASTEXITCODE -eq 0) { $pythonCommand = 'py' }
}
if (-not $pythonCommand -and (Get-Command python -ErrorAction SilentlyContinue)) {
    & python --version *> $null
    if ($LASTEXITCODE -eq 0) { $pythonCommand = 'python' }
}
if (-not $pythonCommand) {
    throw 'Python 3.11 or newer is required. Install Python from python.org, enable the Python launcher, then run this script again.'
}
$versionText = if ($pythonCommand -eq 'py') { (& py -3 --version 2>&1 | Out-String).Trim() } else { (& python --version 2>&1 | Out-String).Trim() }
if ($versionText -notmatch 'Python\s+(\d+)\.(\d+)') { throw "Could not read Python version: $versionText" }
if ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 11)) {
    throw "Python 3.11 or newer is required; found $versionText. Install a supported Python and retry."
}

$venvPython = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'Creating an isolated Aesculyn Python environment...'
    if ($pythonCommand -eq 'py') { & py -3 -m venv .venv } else { & python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
}

Write-Host 'Checking the pinned app dependencies (first launch may need internet access)...'
& $venvPython -c "import numpy, pandas, threadpoolctl" *> $null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install -r (Join-Path $project 'requirements-research-lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check internet access and rerun this launcher.' }
}

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
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/" }
& $venvPython (Join-Path $project 'app.py')
if ($LASTEXITCODE -ne 0) { throw 'Aesculyn stopped with an error. Read the message above and fix the indicated Python or dependency issue.' }
