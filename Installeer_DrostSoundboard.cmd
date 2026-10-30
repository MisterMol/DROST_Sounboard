@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title DrostSoundboard installeren
if not exist "%~dp0hulpmiddelen\installeer_drost_release.ps1" (
    echo Installatiehulp ontbreekt. Clone het volledige project opnieuw.
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0hulpmiddelen\installeer_drost_release.ps1"
set "RESULTAAT=%ERRORLEVEL%"
if not "%RESULTAAT%"=="0" echo De installatiehulp is gestopt met een fout. Lees de melding hierboven.
pause
exit /b %RESULTAAT%
