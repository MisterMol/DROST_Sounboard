@echo off
setlocal
cd /d "%~dp0..\.."

if not exist ".venv\Scripts\python.exe" (
    echo De projectomgeving is nog niet gemaakt.
    echo Dubbelklik eerst op Installeer_ontwikkelomgeving.bat.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "main.py"
set "uitkomst=%ERRORLEVEL%"

echo.
if not "%uitkomst%"=="0" (
    echo Er ging iets fout bij de apparaatcontrole.
    echo Bekijk de logs via: %%LOCALAPPDATA%%\DrostSoundboard\logboeken
) else (
    echo De apparaatcontrole is afgerond.
)
echo.
pause
exit /b %uitkomst%
