@echo off
setlocal
cd /d "%~dp0..\.."
if not exist "Update_DrostSoundboard.ps1" (
  echo Update_DrostSoundboard.ps1 ontbreekt in deze map.
  pause
  exit /b 1
)
rem Draai alleen het vertrouwde, lokale script. We wijzigen geen systeembeleid.
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%CD%\Update_DrostSoundboard.ps1" %*
set "resultaat=%ERRORLEVEL%"
if not "%resultaat%"=="0" (
  echo.
  echo Bijwerken is niet geslaagd. Bekijk de fout hierboven en het updatelog.
)
echo.
pause
exit /b %resultaat%
