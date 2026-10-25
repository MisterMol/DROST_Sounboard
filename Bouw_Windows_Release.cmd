@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0Bouw_Windows_Release.ps1" %*
if errorlevel 1 (
    echo.
    echo De bouw is mislukt. Lees de foutmelding hierboven.
)
echo.
pause
