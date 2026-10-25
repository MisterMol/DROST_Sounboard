@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo DrostSoundboard kan nog niet starten. Dubbelklik eerst op Installeer_ontwikkelomgeving.bat.
    pause
    exit /b 1
)
rem Start de DESKTOPAPP: de webpagina mag daarna dicht.
rem Een tweede dubbelklik opent alleen het bestaande lokale dashboard.
start "" ".venv\Scripts\pythonw.exe" "%~dp0start_desktop.py"
exit /b 0
