@echo off
SETLOCAL

echo ========================================
echo  Heidi Archival System - Local Runner
echo  Mode: VISIBLE CHROME (Non-Headless)
echo ========================================
echo.

REM Check Python
where python >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found. Install Python 3.11+ from https://python.org and add to PATH.
    pause
    exit /b 1
)

REM Change to the backend directory
IF NOT EXIST "%~dp0backend\heidi_exporter" (
    echo ERROR: Backend directory not found. Please run this script from inside the Heidi_Session_Archival_System folder.
    pause
    exit /b 1
)
cd /d "%~dp0backend\heidi_exporter"

REM Create venv if missing
IF NOT EXIST ".venv" (
    echo SETUP: Creating Python virtual environment...
    python -m venv .venv
)

REM Activate venv
call .venv\Scripts\activate.bat

REM Install dependencies
echo SETUP: Installing dependencies (this may take a moment the first time)...
pip install -r requirements.txt -q

REM Check and download spacy model if needed
echo SETUP: Checking NLP model...
python -c "import spacy; spacy.load('en_core_web_lg')" 2>nul || python -m spacy download en_core_web_lg

REM Force non-headless so Chrome window is visible
SET HEADLESS=false
echo INFO: HEADLESS=false — Chrome window will open on your desktop!
echo INFO: You can watch every click, scroll, and extraction in real time.
echo.

IF "%1"=="--reset" (
    echo MODE: Resetting archive database and checkpoint...
    python main.py --reset-archive
    goto :end
)

IF "%1"=="--discover-only" (
    echo MODE: Discovery only — no transcript/note extraction...
    python main.py --discover-only
    goto :end
)

IF "%1"=="--export-only" (
    echo MODE: Export only — generating CSV/JSON from existing database...
    python main.py --export-only
    goto :end
)

echo MODE: Full archive run...
echo INFO: Press Ctrl+C at any time to stop. Progress is saved automatically.
echo.
python main.py

:end
echo.
echo DONE: Scraper finished.
pause
ENDLOCAL
