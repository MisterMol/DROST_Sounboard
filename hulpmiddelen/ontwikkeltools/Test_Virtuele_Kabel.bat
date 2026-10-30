@echo off
setlocal
cd /d "%~dp0..\.."

if not exist ".venv\Scripts\python.exe" (
    echo De Python-projectomgeving ontbreekt nog.
    echo Start eerst Installeer_ontwikkelomgeving.bat.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "controleer_virtuele_kabel.py"
set "uitkomst=%ERRORLEVEL%"

echo.
if not "%uitkomst%"=="0" (
    echo De kabeltest heeft geen succes bevestigd.
    echo Bekijk de uitvoer hierboven en de logmap via Open_Logboeken.bat.
) else (
    echo De eerste kabeltest is geslaagd.
)
echo.
pause
exit /b %uitkomst%
