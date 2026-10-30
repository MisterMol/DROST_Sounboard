@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title DrostSoundboard installeren

rem De map van deze CMD is de basis. Geen gebruikersnaam, Downloads of .git nodig.
set "DROST_SCRIPT=%~dp0hulpmiddelen\installeer_drost_release.ps1"
if not exist "%DROST_SCRIPT%" (
    echo.
    echo Installatiehulp ontbreekt: hulpmiddelen\installeer_drost_release.ps1
    echo Download of clone het volledige project opnieuw.
    pause
    exit /b 1
)

where powershell.exe >nul 2>nul
if errorlevel 1 (
    echo Windows PowerShell ontbreekt of is niet beschikbaar via PATH.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DROST_SCRIPT%"
set "RESULTAAT=%ERRORLEVEL%"
if not "%RESULTAAT%"=="0" (
    echo.
    echo Installatie niet voltooid. Lees de melding hierboven.
)
echo.
pause
exit /b %RESULTAAT%
