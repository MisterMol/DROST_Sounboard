@echo off
setlocal
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" (
    echo Draai eerst Installeer_ontwikkelomgeving.bat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "%CD%\start_desktop.py"
if errorlevel 1 (
    echo Bekijk software.jsonl in de logmap voor de volledige fout.
    pause
)
