$ErrorActionPreference = "Stop"

# Run FF Arena's project-owned AI workers on this Windows PC.
# This uses the existing local .env; never put secrets in this script or GitHub.

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Test-Path (Join-Path $repoRoot ".env"))) {
    throw "Missing .env. Copy .env.example to .env and configure Django/database/LiveKit values locally."
}

if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    throw "Tesseract OCR is not installed or not in PATH. Install the free Tesseract OCR engine, reopen PowerShell, then run this script again."
}

python --version
if ($LASTEXITCODE -ne 0) { throw "Python is not available in PATH." }

python manage.py check
if ($LASTEXITCODE -ne 0) { throw "Django system check failed. Fix the errors before starting AI." }

# Check the two existing local worker commands before starting long-running windows.
python manage.py live_ai_worker --help
if ($LASTEXITCODE -ne 0) { throw "Live AI worker command could not be loaded." }
python manage.py live_ai_payment_worker --help
if ($LASTEXITCODE -ne 0) { throw "Payment AI worker command could not be loaded." }

$liveCommand = "Set-Location '$($repoRoot.Replace("'","''"))'; python manage.py live_ai_worker --poll-seconds 5"
$paymentCommand = "Set-Location '$($repoRoot.Replace("'","''"))'; python manage.py live_ai_payment_worker --poll-seconds 5"

Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $liveCommand)
Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $paymentCommand)

Write-Host "FF Arena local AI workers started in two PowerShell windows." -ForegroundColor Green
Write-Host "Live AI reads eligible BR/VS LiveKit streams. Payment AI only assesses candidates."
Write-Host "Wallet auto-credit is not performed by either worker. Admin approval remains required."
