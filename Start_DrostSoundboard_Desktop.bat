@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo De ontwikkelomgeving ontbreekt. Voer eerst Installeer_ontwikkelomgeving.bat uit.
    pause
    exit /b 1
)
rem Gebruik pythonw om geen permanent consolevenster open te houden.
rem Start maar EEN proces: een tweede dubbelklik opent alleen het dashboard.
start "" ".venv\Scripts\pythonw.exe" "%~dp0start_desktop.py"
exit /b 0
