# DrostSoundboard 5.9.2: bediening, MP4-consolevensters en headsetmonitor

Deze herstelupdate is bedoeld voor DrostSoundboard 5.9.1. Je bestaande SQLite-bibliotheek, gebruikersinstellingen, favorieten, sneltoetsen en logboeken worden niet vervangen.

## Wat is opgelost?

* In de lege speler zijn **Stop** en **Preview stoppen** niet actief. De knoppen zijn ook visueel gedempt. Ze worden actief wanneer een preview, livefragment of voorbereidingsactie loopt.
* Probeer je een effect naar een call te sturen terwijl de effecten uit staan, dan markeert het dashboard de schakelaar **Geluidseffecten** tijdelijk met een rode rand. De pagina scrolt er rustig naartoe. Ben je niet verbonden, dan wordt **Verbinden** aangewezen. Bij een bewegingsbeperking gebruikt de pagina geen onnodige scrollanimatie.
* De meegeleverde MP4-decoder wordt direct uit de Windows-package gevonden. Een verborgen interne `ffmpeg -version`-controle die alsnog een zwart consolevenster kon openen, is niet meer nodig. Alle eigen FFmpeg-aanroepen gebruiken daarnaast al `CREATE_NO_WINDOW`.
* Bij veel snelle Stop-acties kan de headsetmonitor geen buffer meer halverwege de audiocallback naar `None` veranderen. Het leegmaken wordt in een generatie opgeslagen en door de audiocallback zelf verwerkt. Dit voorkomt de eerder waargenomen `TypeError: object of type 'NoneType' has no len()`.

## Installeren

1. Sluit DrostSoundboard via het systeemvak, niet alleen het browsertabblad.
2. Sla `DrostSoundboard_5_9_2_Herstel_Update.zip` op in Downloads.
3. Open PowerShell en voer uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests `
  -DestinationPath .\DrostSoundboard_backup_voor_592.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_5_9_2_Herstel_Update.zip" `
  -DestinationPath . -Force

cd .\DrostSoundboard
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Bij de geteste broncode worden **294 tests** gevonden en slagen die; optionele tests kunnen op Windows worden overgeslagen.

4. Start DrostSoundboard met je bestaande bureaubladsnelkoppeling, dus niet via de ontwikkelbatch. Ververs de browser één keer met `Ctrl + Shift + R`.

## Controleren

1. Als niets afspeelt, moeten beide Stop-knoppen grijs en uitgeschakeld zijn.
2. Klik op een favoriet met Soundboard uit. De applicatie moet de schakelaar aanwijzen, zonder de verbinding met VB-CABLE te verbreken.
3. Sluit de webpagina, laat het achtergrondprogramma actief en controleer of je sneltoetsen blijven werken.
4. Importeer of bewerk een MP4 en probeer Preview, Stop en een andere MP4 na elkaar. De FFmpeg-consoles horen niet op te lichten. Dit moet nog op Windows 11 worden bevestigd.
5. Herhaal snelle Stop-acties. Er mag geen Python-CFFI-foutvenster verschijnen.

Bij een resterend probleem kun je de laatste regels uit `%LOCALAPPDATA%\DrostSoundboard\logboeken\software.jsonl` delen. De foutafhandeling blijft ingeschakeld. Schakel Windows-beveiliging niet uit om de patch te installeren.

## Technische grenzen

De Python- en browsertests zijn uitgevoerd zonder de fysieke Razer en Windows-desktop. De combinatie met het echte Windows-systeemvak, VB-CABLE en eventuele antivirustoepassingen vraagt nog een praktijktest. Door deze update worden de audiomixer en apparatenkeuze zelf niet gewijzigd.
