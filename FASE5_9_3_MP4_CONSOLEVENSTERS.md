# DrostSoundboard 5.9.3: MP4-consolevensters

Deze kleine update verandert alleen de manier waarop FFmpeg als extern proces
start, maakt de geladen appversie zichtbaar en voegt regressietests toe.
De audiomixer, het afspelen van geluiden, de database en alle gebruikersgegevens
blijven ongewijzigd.

## Waarom deze wijziging?

Op Windows kan een consoleprogramma kort een venster openen, ook als de
hoofdapplicatie via `pythonw.exe` draait. Eerdere versies gebruikten al
`CREATE_NO_WINDOW`; versie 5.9.3 gebruikt daarnaast `STARTUPINFO` met
`STARTF_USESHOWWINDOW` en `SW_HIDE`. FFmpeg-uitvoer en Python-tracebacks worden
nog steeds verwerkt en gelogd.

**Let op:** deze code is automatisch getest, maar het specifieke flitsende venster
kan alleen op de Windows-pc worden beoordeeld. Een venster dat door een ander
programma wordt gemaakt valt buiten deze aanpassing.

## Bijwerken

1. Sluit DrostSoundboard via **Afsluiten** in het systeemvak. Sluit alleen de
   browser niet: dan blijft de oude Python-code in het geheugen draaien.
2. Voer deze opdrachten uit in PowerShell:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"
Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\start_desktop.py -DestinationPath .\DrostSoundboard_backup_voor_593.zip -Force
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_5_9_3_Update.zip" -DestinationPath . -Force
cd .\DrostSoundboard
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

De testsuite moet eindigen met `Ran 295 tests` en `OK`. Op Windows kan één of
meer tests worden overgeslagen.

3. Start DrostSoundboard via de bureaubladsnelkoppeling (dus niet via een `.bat`).
4. Controleer dat je daadwerkelijk de nieuwe code gebruikt:

```powershell
$gegevens = Get-Content "$env:LOCALAPPDATA\DrostSoundboard\actieve_desktopinstantie.json" -Raw -Encoding UTF8 | ConvertFrom-Json
Invoke-RestMethod "http://127.0.0.1:$($gegevens.poort)/api/versie" | Format-List
```

Je moet `versie : 5.9.3-console-diagnose` zien. Als deze route niet bestaat of
nog een oude versie toont, draait er nog een eerder gestart achtergrondproces.
Sluit dat eerst via het systeemvak af, en start dan opnieuw.

## Test

1. Open een MP4-fragment, bijvoorbeeld het bestaande `Goodbye Kyle`.
2. Start en stop enkele keren, zonder in een Discord-gesprek te zitten.
3. Controleer of er nog een zwart of transparant consolevenster in beeld flitst.
4. Controleer of de audio nog steeds via VB-CABLE wordt verzonden.

Als het venster blijft verschijnen **terwijl de versiecheck 5.9.3 toont**, is
nog niet bewezen welk uitvoerbaar bestand het aanmaakt. Dan moeten we de
processen op die Windows-pc registreren. Houd de eerste seconden van een
schermopname en het tijdstip bij. DrostSoundboard blijft fouten in
`%LOCALAPPDATA%\DrostSoundboard\logboeken\software.jsonl` opslaan.

## Voor ontwikkelaars

Voer na wijzigingen altijd de tests uit. Gebruik voor nieuwe aanroepen van
externe consoleprogramma's de bestaande functie
`geef_opstartopties_zonder_console()` en geef de argumenten direct aan
`subprocess.run()`. Gebruik geen `shell=True` of onzichtbare processpawns
zonder logging. De helper maakt voor iedere aanroep een eigen STARTUPINFO,
omdat we die niet tussen meerdere gelijktijdige decodeertaken willen delen.
