# DrostSoundboard Updater 1.2: herstel van procesherkenning

Deze patch wijzigt **alleen** de ontwikkel-updater, de drie start-batchbestanden en documentatie. De audiomotor, bibliotheek en gebruikersgegevens blijven staan. De appversie blijft 5.9.4; de updater krijgt revisie 1.2.

## Wat was er mis?

In Python 3.13 start de virtuele Windows-Pythonomgeving (`.venv`) vaak via een redirector. Daardoor kan `Win32_Process.ExecutablePath` voor het echte programma naar de basis-Pythoninstallatie wijzen, terwijl `Start-Process` de venv-starter teruggeeft. Bijvoorbeeld de starter met PID 15420 en de echte desktopserver met PID 4344.

Updater 1.1 herkende vrijwel uitsluitend de venv-starter. Hij vergeleek die PID met de echte PID uit `actieve_desktopinstantie.json`, keurde de herstart af en herstelde de oude bestanden.

## Verbeteringen

* Herkenning van **zowel** de venv-starter als het echte kindproces, dankzij de interpreterpaden in `.venv\pyvenv.cfg`, de volledige opdrachtregel, het exacte startscript en de Windows-sessie.
* De server-PID uit `actieve_desktopinstantie.json` wordt gekoppeld aan precies één gecontroleerd Windows-proces, daarna moet `/api/versie` exact dezelfde PID en de juiste versie teruggeven.
* De status moet na deze herstart zijn geschreven, het proces moet recent gestart zijn, en moet tijdens de eindcontrole nog leven. Bestaande veiligheidscontrole op PID-hergebruik bij stoppen blijft actief.
* Andere projecten, zelfs wanneer ze `start_desktop.py` heten, worden niet gestopt.
* Start-batchbestanden geven voortaan het absolute pad van `start_desktop.py` mee.
* Een herstart waarvoor geen veilige bevestiging beschikbaar is blijft **mislukt**, inclusief rollback. De updater kiest nooit blind het eerste Python-proces.

## Eenmalig installeren

Pak `DrostSoundboard_Updater_1_2_Procesherstel.zip` uit in de **bovenliggende map** van het bestaande project, zodat de bestanden in `DrostSoundboard\` terechtkomen. Doe dit niet tijdens een belgesprek. Met PowerShell:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Updater_1_2_Procesherstel.zip" -DestinationPath . -Force
cd .\DrostSoundboard
```

Controleer de interne procesherkenning zonder processen te stoppen:

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\tests\Controleer_Updater_Procesbeheer.ps1
```

Controleer daarna of de updater de echt draaiende app vindt:

```powershell
.\Update_DrostSoundboard.cmd -AlleenProcescontrole
```

Gebruik daarna `Update_DrostSoundboard.cmd` voor een nieuwe update. Staat er meer dan één patch in Downloads, gebruik dan liever expliciet:

```powershell
.\Update_DrostSoundboard.cmd -UpdateBestand "$env:USERPROFILE\Downloads\DrostSoundboard_5_9_4_Update.zip"
```

De updater neemt het projectpad automatisch van zijn eigen script. Een Windows-gebruikersnaam is nergens ingebouwd.

## Wat is wel en niet getest?

De procesdetectie heeft een afzonderlijke PowerShell-regressietest met nagebootste Windows-procesmetadata. Die moet op jouw Windows-machine uitgevoerd worden omdat hier geen Windows-kernel en PowerShell 5.1 beschikbaar zijn. De Python-tests controleren onderdelen van de app, maar zijn geen garantie voor drivers, tray of proceslevenscyclus.

De patch is **geen gecompileerde versie 6.0** en vereist nog steeds de ontwikkelomgeving met Python en VB-CABLE. Er is geen code signing of installer toegevoegd.
