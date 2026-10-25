@echo off
setlocal
cd /d "%~dp0"

echo DrostSoundboard, eenmalige voorbereiding ontwikkelomgeving
echo Projectmap: %CD%
echo.

set "logmap=%LOCALAPPDATA%\DrostSoundboard\logboeken"
if not exist "%logmap%" mkdir "%logmap%" >nul 2>&1
set "installatielog=%logmap%\installatie.txt"
echo [%DATE% %TIME%] Installatiecontrole gestart. >> "%installatielog%"
echo Projectmap: %CD% >> "%installatielog%"

py -3.13 --version
if errorlevel 1 (
    echo.
    echo Python 3.13 is niet beschikbaar via de Windows Python Launcher.
    echo Controleer eerst met: py -3.13 --version
    echo [%DATE% %TIME%] Python 3.13 ontbreekt of kon niet gestart worden. >> "%installatielog%"
    goto mislukt
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Eigen Python-omgeving wordt aangemaakt...
    py -3.13 -m venv .venv >> "%installatielog%" 2>&1
    if errorlevel 1 (
        echo De eigen Python-omgeving kon niet worden aangemaakt.
        goto mislukt
    )
)

echo.
echo Benodigde Python-onderdelen worden gecontroleerd en geinstalleerd...
".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%installatielog%" 2>&1
if errorlevel 1 (
    echo Het installeren van Python-onderdelen is mislukt.
    echo Controleer je internetverbinding en het installatiebestand.
    goto mislukt
)

REM Eerst imports controleren voorkomt dat de installer succes meldt maar
REM een later geopende pagina alsnog faalt op een ontbrekende MP3-decoder.
echo Controleren of alle geluidsbibliotheken echt geladen kunnen worden...
".venv\Scripts\python.exe" -c "import sounddevice, numpy, soundfile, soxr, imageio_ffmpeg, PIL, pystray; print('MP3, WAV, MP4 en GIF onderdelen beschikbaar')" >> "%installatielog%" 2>&1
if errorlevel 1 (
    echo Een audiobibliotheek kon niet geladen worden. Zie installatie.txt.
    goto mislukt
)

echo.
echo Installatie geslaagd.
echo [%DATE% %TIME%] Installatie afgerond. >> "%installatielog%"
echo Start de achtergrondapp met Start_DrostSoundboard.bat.
echo Installatielog: %installatielog%
echo.
pause
exit /b 0

:mislukt
echo [%DATE% %TIME%] Installatie gestopt door fout. >> "%installatielog%"
echo.
echo De installatie is niet gelukt. Open dit logbestand voor de precieze uitvoer:
echo %installatielog%
echo.
pause
exit /b 1
