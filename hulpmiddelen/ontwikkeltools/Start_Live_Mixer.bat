@echo off
setlocal
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" (
    echo De ontwikkelomgeving ontbreekt.
    echo Start eerst Installeer_ontwikkelomgeving.bat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" start_live_mixer.py
if errorlevel 1 (
    echo.
    echo De live mixer is gestopt met een fout. Open Open_Logboeken.bat.
    pause
    exit /b 1
)
exit /b 0
