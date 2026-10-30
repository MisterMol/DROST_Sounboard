@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title DrostSoundboard GitHub-controle
where py >nul 2>&1
if not errorlevel 1 (
  py -3.13 -B "%~dp0hulpmiddelen\controleer_git_publicatie.py"
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo Python ontbreekt. Installeer Python 3.13 voor deze GitHub-controle.
    pause
    exit /b 1
  )
  python -B "%~dp0hulpmiddelen\controleer_git_publicatie.py"
)
set "resultaat=%errorlevel%"
if not "%resultaat%"=="0" echo GitHub-controle niet geslaagd. Niet pushen voordat dit is opgelost.
echo.
pause
exit /b %resultaat%
