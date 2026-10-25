@echo off
setlocal
set "logmap=%LOCALAPPDATA%\DrostSoundboard\logboeken"
if not exist "%logmap%" (
    echo De logmap bestaat nog niet. Start eerst Start_DrostSoundboard.bat.
    pause
    exit /b 1
)
start "" explorer.exe "%logmap%"
