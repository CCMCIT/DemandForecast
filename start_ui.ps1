# Double-click start_ui.bat, or right-click this file -> Run with PowerShell.
# First run: builds the virtualenv and installs dependencies.
# Every run: starts the local tester UI at http://localhost:5000.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".\.venv")) {
    Write-Host "First run: creating virtual environment (Python 3.12)..." -ForegroundColor Cyan
    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

$env:PYTHONPATH = "src"
Write-Host "Starting UI at http://localhost:5000 (Ctrl+C to stop)..." -ForegroundColor Green
Start-Process "http://localhost:5000"
.\.venv\Scripts\python.exe -m app.entrypoints.web
