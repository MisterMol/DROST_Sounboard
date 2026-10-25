@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo De Python-omgeving ontbreekt.
    echo Start eerst Installeer_ontwikkelomgeving.bat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" diagnoseer_microfoon.py
if errorlevel 1 (
    echo.
    echo De test gaf een fout of zag geen duidelijk signaal.
    echo Kijk in de uitvoer en in software.jsonl voor de oorzaak.
)
echo.
pause
