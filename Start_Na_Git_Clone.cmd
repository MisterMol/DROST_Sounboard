@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title DrostSoundboard vanuit broncode

echo DrostSoundboard, starten vanuit een GitHub-clone
echo.
echo Dit is de ontwikkelroute. Voor vrienden is de Windows Setup op GitHub Releases eenvoudiger.
echo https://github.com/MisterMol/DROST_Sounboard/releases
echo.

if not exist "app\audio\native\win-x64\drost_stem.dll" goto ontbrekende_stem
if not exist "stem-runtime\DrostStemWorker.exe" goto ontbrekende_stem
if not exist "stem-runtime\G_500000.pth" goto ontbrekende_stem

echo Alle vereiste stemonderdelen lijken aanwezig. Bestandscontroles volgen bij gebruik.
if not exist ".venv\Scripts\python.exe" (
  echo Pythonomgeving ontbreekt. De eenmalige installatie wordt gestart.
  call "%~dp0Installeer_ontwikkelomgeving.bat"
  if errorlevel 1 goto mislukt
)
if not exist ".venv\Scripts\python.exe" goto mislukt
call "%~dp0Start_DrostSoundboard_Desktop.bat"
exit /b 0

:ontbrekende_stem
echo De clone bevat geen volledige stemmotor en geen modelgewichten.
echo Alleen de broncode klonen is dus niet genoeg voor alle functies.
echo Download voor gewoon gebruik de complete Windows Setup via GitHub Releases.
echo De broncode is wel geschikt om te lezen, testen en verbeteren.
echo.
choice /C JN /N /M "Open GitHub Releases in je browser? [J/N] "
if errorlevel 2 exit /b 2
start "" "https://github.com/MisterMol/DROST_Sounboard/releases"
exit /b 2

:mislukt
echo.
echo Installatie of start is mislukt. Lees de melding hierboven.
pause
exit /b 1
