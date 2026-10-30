@echo off
setlocal
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" (
    echo De eigen Python-omgeving is niet gevonden.
    echo Start eerst Installeer_ontwikkelomgeving.bat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" controleer_opnamekant_van_cable.py
set "RESULTAAT=%ERRORLEVEL%"
echo.
if not "%RESULTAAT%"=="0" echo Kijk hierboven naar de diagnose en stuur zo nodig de nieuwe logboeken.
pause
exit /b %RESULTAAT%
