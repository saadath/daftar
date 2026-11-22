@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.14 -m venv .venv
    if errorlevel 1 (
        echo Python 3.14 is required. Install Python and try again.
        pause
        exit /b 1
    )
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (
        pause
        exit /b 1
    )
)
.venv\Scripts\python.exe main.py
if errorlevel 1 pause
