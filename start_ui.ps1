# Double-click start_ui.bat, or right-click this file -> Run with PowerShell.
# First run: builds the virtualenv and installs dependencies.
# Every run: starts the local tester UI at http://localhost:5000.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# A valid venv has both python.exe and pyvenv.cfg; check both so a partial or
# corrupt .venv (e.g. missing pyvenv.cfg) is rebuilt instead of silently skipped.
$venvValid = (Test-Path ".\.venv\Scripts\python.exe") -and (Test-Path ".\.venv\pyvenv.cfg")
if (-not $venvValid) {
    if (Test-Path ".\.venv") {
        Write-Host "Removing incomplete .venv..." -ForegroundColor Yellow
        try {
            Remove-Item -Recurse -Force ".\.venv" -ErrorAction Stop
        } catch {
            Write-Host "Could not remove .\.venv - a file is likely in use." -ForegroundColor Red
            Write-Host "Close any running python.exe (or this app) that may be using it, then run this script again." -ForegroundColor Red
            Read-Host "Press Enter to exit"
            exit 1
        }
    }
    Write-Host "First run: creating virtual environment (Python 3.12)..." -ForegroundColor Cyan
    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

$env:PYTHONPATH = "src"
Write-Host "Starting UI at http://localhost:5000 (Ctrl+C to stop)..." -ForegroundColor Green
Start-Process "http://localhost:5000"
.\.venv\Scripts\python.exe -m app.entrypoints.web
