#!/usr/bin/env pwsh
# Heidi Archival System — Local Windows Runner (PowerShell)
# Runs the scraper with a VISIBLE Chrome window for full transparency.

$ErrorActionPreference = "Stop"
$BackendDir = Join-Path $PSScriptRoot "backend\heidi_exporter"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Heidi Archival System - Local Runner  " -ForegroundColor Cyan
Write-Host "  Mode: VISIBLE CHROME (Non-Headless)  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install Python 3.11+ from https://python.org and add to PATH." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $BackendDir)) {
    Write-Host "ERROR: Backend directory not found. Please run this script from inside the Heidi_Session_Archival_System folder." -ForegroundColor Red
    exit 1
}

Set-Location $BackendDir

# Create venv if missing
if (-not (Test-Path ".venv")) {
    Write-Host "SETUP: Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate venv
& ".venv\Scripts\Activate.ps1"

# Install dependencies
Write-Host "SETUP: Installing dependencies (this may take a moment the first time)..." -ForegroundColor Yellow
pip install -r requirements.txt -q

# Check and download spacy model if needed
Write-Host "SETUP: Checking NLP model..." -ForegroundColor Yellow
python -c "import spacy; spacy.load('en_core_web_lg')" 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m spacy download en_core_web_lg
}

# Force non-headless so Chrome window is visible
$env:HEADLESS = "false"
Write-Host "INFO: HEADLESS=false — Chrome window will open on your desktop!" -ForegroundColor Green
Write-Host "INFO: You can watch every click, scroll, and extraction in real time." -ForegroundColor Green
Write-Host ""

if ($args -contains "--reset") {
    Write-Host "MODE: Resetting archive database and checkpoint..." -ForegroundColor Magenta
    python main.py --reset-archive
}
elseif ($args -contains "--discover-only") {
    Write-Host "MODE: Discovery only — no transcript/note extraction..." -ForegroundColor Cyan
    python main.py --discover-only
}
elseif ($args -contains "--export-only") {
    Write-Host "MODE: Export only — generating CSV/JSON from existing database..." -ForegroundColor Cyan
    python main.py --export-only
}
else {
    Write-Host "MODE: Full archive run..." -ForegroundColor Green
    Write-Host "INFO: Press Ctrl+C at any time to stop. Progress is saved automatically." -ForegroundColor DarkGray
    Write-Host ""
    python main.py
}

Write-Host ""
Write-Host "DONE: Scraper finished." -ForegroundColor Green
