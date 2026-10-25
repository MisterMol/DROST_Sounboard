# DrostSoundboard 5.1: vloeiende geluidsmeters

Deze update verandert **alleen de twee niveaumeters** en de manier waarop hun geluidsniveaus worden samengevat. De audioverbinding, bibliotheek, favorieten, groepen, mediaplayer en maximaal 120 seconden per fragment blijven ongewijzigd.

## Wat is anders?

De audiomixer meet nu elke tweede callback het werkelijke RMS-geluidsniveau en de samplepiek. Voor de zichtbare RMS-waarde worden alleen de recente audioblokken van ongeveer 160 milliseconden meegenomen. De piekmarkering kijkt ongeveer 350 milliseconden terug, zodat korte geluiden niet verdwijnen tussen twee verzoeken van de browser.

De browser ontvangt nog steeds ongeveer vijf keer per seconde een statusupdate. Hij tekent alleen de tussenliggende beweging met `requestAnimationFrame`. Als de audio harder wordt, reageert de balk snel. Als de audio zachter wordt, loopt de balk rustiger terug. De dunne witte markering toont een daadwerkelijk gemeten recente samplepiek. De decibelberekening volgt precies de zichtbare schaal van min 60 tot 0 dBFS.

De meter bij **Naar VB-CABLE** toont nog steeds wat Python probeert uit te sturen. Dit is niet hetzelfde als een meting bij CABLE Output of een garantie dat Discord het ontvangt.

De audio zelf wordt niet vertraagd of aangepast. Er worden geen spraakopnames opgeslagen. De bestaande auditlogging en tracebacks blijven werken.

## Installeren op je bestaande Windows-pc

1. Sluit DrostSoundboard volledig, ook het PowerShell-venster waarin de webserver draait.
2. Download `DrostSoundboard_Fase5_1_Meters_Update.zip` naar Downloads.
3. Open PowerShell en voer de volgende commando's uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_meters.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase5_1_Meters_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard

.\.venv\Scripts\python.exe -m unittest discover -s tests -q

.\Start_DrostSoundboard.bat
```

Een installatie met pip is niet nodig. De bestaande bestanden in je lokale database blijven staan.

## Controleer de meters

1. Klik op **Verbinden**. Praat normaal in je microfoon. De microfoonmeter en de meter naar VB-CABLE moeten soepel bewegen, met een snelle opwaartse beweging en een iets tragere terugval.
2. Schakel Soundboard in en speel een kort MP3-geluid. Beide meters moeten reageren; tijdens korte pieken zie je ook de dunne piekmarkering.
3. Stop het geluid. Beide meters blijven je microfoon tonen zolang die verbonden is.
4. Open het dashboard opnieuw met `Ctrl + Shift + R` als je browser nog de oude CSS of JavaScript laat zien.

Als de meters niet reageren, controleer `software.jsonl` via `Open_Logboeken.bat`. Bij een antivirusmelding schakel je de beveiliging niet uit, maar onderzoek je eerst welke detectie er is gedaan.

## Bijdragen aan de code

De meterberekening staat in `app/audio/geschiedenis_van_audioniveaus.py`. De browseranimatie staat in duidelijk benoemde functies in `app/webinterface/statisch/dashboard.js`. De piekmarkeringen staan in `dashboard.html` en `stijl.css`. Houd microfoonopnames uit logboeken en schrijf bij een technische keuze niet alleen op wat de code doet, maar ook waarom.
