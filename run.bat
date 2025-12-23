@echo off
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

echo ========================================
echo Starting AI Stock Scorer
echo ========================================

if exist "%PROJECT_ROOT%\venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%\venv\Scripts\activate.bat"
    cd /d "%SCRIPT_DIR%"
    python run_scorer.py
) else (
    echo Virtual environment 'venv' not found.
    pause
    exit /b 1
)

