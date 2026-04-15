@echo off
cd /d "F:\Projects\CSVGenerator2.0"
if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found at .venv\Scripts\python.exe
    echo Recreate it and install requirements before running this launcher.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
pause
