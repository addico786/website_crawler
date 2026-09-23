@echo off
title Website Crawler Dashboard
echo ========================================================
echo        Website Crawler - Non-Technical Dashboard
echo ========================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH!
    echo Please install Python 3.9+ and try again.
    pause
    exit /b 1
)

REM Check or create virtual environment if needed
if not exist "env\" (
    echo Creating virtual environment 'env'...
    python -m venv env
)

REM Activate virtualenv if present
if exist "env\Scripts\activate.bat" (
    call env\Scripts\activate.bat
)

echo Installing/checking required packages...
python -m pip install -r requirements.txt >nul 2>&1
python -m playwright install chromium >nul 2>&1

echo.
echo Starting Dashboard Server at http://localhost:8000 ...
echo Press Ctrl+C in this window to stop the server anytime.
echo.

start http://localhost:8000
python server.py

pause
