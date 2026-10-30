@echo off
setlocal
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\pythonw.exe" (
    echo DrostSoundboard kan nog niet worden gestart.
    echo Voer eerst Installeer_ontwikkelomgeving.bat uit.
    pause
    exit /b 1
)
rem Alleen EENMALIG de Windows-snelkoppeling maken.
rem Daarna start een dubbelklik op de snelkoppeling direct pythonw,
rem zonder cmd.exe, PowerShell of onnodige administratorrechten.
set "DROST_PROJECTMAP=%CD%\"
powershell.exe -NoProfile -Command "$basis=$env:DROST_PROJECTMAP; $python=Join-Path $basis '.venv\Scripts\pythonw.exe'; $programma=Join-Path $basis 'start_desktop.py'; $bureaublad=[Environment]::GetFolderPath('Desktop'); $snelkoppeling=Join-Path $bureaublad 'DrostSoundboard.lnk'; $shell=New-Object -ComObject WScript.Shell; $link=$shell.CreateShortcut($snelkoppeling); $link.TargetPath=$python; $link.Arguments=([char]34)+$programma+([char]34); $link.WorkingDirectory=$basis; $link.Description='DrostSoundboard openen zonder terminalvenster'; $link.Save(); Write-Host ('Snelkoppeling gemaakt: '+$snelkoppeling)"
if errorlevel 1 (
    echo Snelkoppeling maken is mislukt. Controleer de bovenstaande foutmelding.
    pause
    exit /b 1
)
echo Start voortaan DrostSoundboard via het nieuwe bureaubladpictogram.
pause
exit /b 0
