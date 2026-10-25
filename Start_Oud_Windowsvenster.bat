@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Voer eerst Installeer_ontwikkelomgeving.bat uit.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" start_live_mixer.py
if errorlevel 1 pause
