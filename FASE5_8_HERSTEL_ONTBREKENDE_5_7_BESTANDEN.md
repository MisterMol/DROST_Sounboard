# DrostSoundboard 5.8 herstelupdate

Deze herstelupdate repareert een onvolledige overgang van versie 5.6.1 naar 5.8.
Alle ontbrekende 5.7-bestanden en de 5.8-wijzigingen zijn samengevoegd.

De eerdere testfout was:
`TypeError: geef_mogelijke_exportformaten() got an unexpected keyword argument 'bron'`

De update overschrijft alleen broncode, documentatie en tests in de projectmap.
SQLite-bibliotheek, favorieten, geluidsbestanden, .venv en logbestanden worden niet verwijderd.

## Stappen

1. Sluit DrostSoundboard en de Python-webserver volledig af.
2. Open PowerShell en maak een back-up (zie ook de uitleg in de ChatGPT-respons).
3. Controleer de downloadnaam en pak het ZIP-bestand uit in `pythonProjects`, niet in de bestaande `DrostSoundboard`-map:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_5_8_Herstel_Update.zip" -DestinationPath . -Force
cd .\DrostSoundboard
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Verwacht: `Ran 262 tests` en `OK`.

4. Start met ` .\Start_DrostSoundboard.bat` en ververs de browser met `Ctrl + Shift + R`.

## Als je opnieuw HTTP 500 krijgt

Bekijk `software.jsonl` via `Open_Logboeken.bat`.
Als Windows een van de bestanden in quarantaine heeft geplaatst, controleer de detectie voordat je het opnieuw probeert. Schakel beveiliging niet uit.
