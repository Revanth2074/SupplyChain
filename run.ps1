# One-command setup and launch on a new Windows machine (PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
# First run: creates backend\.venv, installs the pinned dependencies and checks backend\.env.
# Every run: starts the API + console on http://127.0.0.1:8000 (Ctrl+C to stop).
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "[*] Creating virtual environment (Python 3.11+ required)..."
    $launcher = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
    & $launcher -m venv (Join-Path $backend ".venv")
    & $py -m pip install --upgrade pip
    Write-Host "[*] Installing dependencies (a few minutes the first time)..."
    & $py -m pip install -r (Join-Path $backend "requirements.txt") -c (Join-Path $backend "constraints.txt")
}

$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $backend ".env.example") $envFile
    Write-Host "[!] Created backend\.env from .env.example. Fill in the Synapt credentials and the judge LLM key, then run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host "[*] Starting on http://127.0.0.1:$Port  (API docs: /docs)"
Push-Location $backend
try { & $py -m uvicorn server:app --host 127.0.0.1 --port $Port }
finally { Pop-Location }
