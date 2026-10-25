# DrostSoundboard 5.0: donker dashboard, groepen en fragmenteditor

Deze versie vervangt de vormgeving van fase 4 en breidt de bibliotheek uit. De bestaande microfoonmixer en de verbinding naar VB-CABLE blijven intact. Alles draait lokaal op de eigen Windows-pc.

## Wat is toegevoegd?

- Een nieuwe, rustige donkere stijl met duidelijke niveau-indicatoren in dBFS en soepele animaties. Zonder externe frontendbibliotheek.
- Vijftien vaste favorieten die op een kleiner scherm automatisch naar minder kolommen gaan, zonder dat de volgorde verandert.
- **Groepen**, bijvoorbeeld `South Park`, `Discord` of `Muziek`. Een geluid kan in meerdere groepen zitten en blijft altijd ook in de volledige bibliotheek staan.
- Een fragmenteditor met een begin- en eindmarkering, een echte audiogolfvorm van het geselecteerde gebied, een lokale preview, volume, groepskeuzes en afbeelding/GIF/video-instellingen.
- Een fragment kan maximaal **120 seconden** duren. Een bestand van 29 seconden wordt ook getoond als **0:29**, niet als 2:00.
- Bij één geïmporteerd bestand opent de editor meteen. Importeer je meerdere bestanden tegelijk, dan bewerk je ze daarna via de drie puntjes.
- MP4 krijgt bij het importeren een kleine, stilstaande PNG-miniatuur als FFmpeg die kan maken. De video zelf speelt alleen in het actieve beeldvak.
- De browser registreert JavaScript-fouten met stacktrace in de softwarelogging, naast de bestaande Python-tracebacks.

## 1. Veilig installeren

Sluit eerst DrostSoundboard, ook het terminalvenster. Voer daarna PowerShell uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.py,.\DrostSoundboard\*.bat,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_fase5.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase5_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard
```

De update vervangt geen persoonlijke SQLite-bestanden of bestaande logboeken in `%LOCALAPPDATA%`. De Python-omgeving `.venv` blijft behouden en er zijn geen nieuwe Python-pakketten nodig ten opzichte van fase 4.

Als Windows opnieuw een download blokkeert met een malwaremelding, schakel de beveiliging dan **niet** uit. Zoek eerst de detectienaam in Windows-beveiliging en onderzoek die voordat het pakket wordt uitgevoerd.

## 2. Controleer de bestanden en tests

```powershell
Test-Path .\app\webinterface\statisch\dashboard.js
Test-Path .\app\webinterface\geluidsgroepen.py
Test-Path .\app\audio\bronduur_en_golfvorm.py

.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

De drie `Test-Path`-commando's moeten `True` geven. In de ontwikkelomgeving zijn 175 tests geslaagd. Dat is geen vervanging voor een test op de echte Razer, VB-CABLE en browser van de gebruiker.

## 3. Start het dashboard

```powershell
.\Start_DrostSoundboard.bat
```

De browser opent het lokale dashboard op `http://127.0.0.1:8765/`, of op een vrije poort als 8765 al bezet is. Laat het terminalvenster open. Het audioproces stopt wanneer je de server afsluit.

## 4. Maak een South Park-groep

1. Kijk rechts in het dashboard onder **Groepen**.
2. Klik op **Nieuwe groep**.
3. Geef als naam `South Park` op.
4. Selecteer in de bibliotheek een South Park-geluid en klik op de drie puntjes.
5. Vink onder **Groepen** de groep **South Park** aan en klik op **Wijzigingen opslaan**.
6. Klik rechts op **South Park**. Je ziet alleen de geluiden uit deze groep.
7. Klik op **Alle geluiden** om de hele bibliotheek weer te tonen.

Een geluid mag in meerdere groepen staan. Je kunt het ook direct vanuit de bibliotheek naar een groepsfilter verslepen. De drie puntjes bij een groep laten de naam veranderen of de groep verwijderen. Groepen verwijderen wist nooit de MP3, MP4, WAV of favoriet.

## 5. Een geluid importeren en inkorten

1. Klik op **Bestanden toevoegen** en kies één MP3, WAV of MP4.
2. Na het importeren opent automatisch de fragmenteditor.
3. Controleer het label **Bron**. Bij een bestand van exact 29 seconden hoort `Bron 0:29` te staan.
4. Gebruik de twee markeringen onder de golfvorm om het start- en eindpunt te kiezen. Je kunt de tijden ook nauwkeurig in seconden invoeren.
5. Klik op **Preview selectie** om het geselecteerde stukje **alleen lokaal in je browser** te horen. De andere gesprekspartij hoort deze editor-preview niet.
6. Stel eventueel het volume, de groep en een afbeelding of GIF in.
7. Klik op **Wijzigingen opslaan**. Het originele bronbestand wordt niet ingekort of overschreven. Alleen de beginpositie en de duur staan in SQLite.

Een lang nummer kan bijvoorbeeld beginnen op 1:40 en 1:10 duren. De selectie is begrensd op 2:00. Is de bron nog maar 0:29 lang, dan toont de bibliotheek 0:29 als daadwerkelijke afspeelduur.

## 6. Afspelen versus preview

**Preview:** via de browser naar je standaard Windows-geluidsuitvoer, zonder VB-CABLE.

**Echt afspelen:** via de Python-mixer naar VB-CABLE. Wanneer **Meeluisteren** aan staat, krijg je het effect ook via je gekozen headset. De fysieke microfoon wordt niet opnieuw op de headset gezet, om echo te voorkomen.

**Stoppen:** het geluid en de actieve video/GIF stoppen, de microfoonverbinding blijft bestaan.

Gebruik in Discord **CABLE Output (VB-Audio Virtual Cable)** als **invoerapparaat** en de Razer USB Sound Card als **uitvoerapparaat**. Je Windows-standaardmicrofoon mag de Razer blijven. Controleer in een echt gesprek of iemand het hoort.

## 7. MP4, GIF en foto's

Bij een MP4 blijft het volledige originele mediabestand intact. De browser toont het bewegende videobeeld terwijl Python de audio via de mixer afspeelt. Bij een gekoppelde GIF of foto kies je in de editor **Afbeelding of GIF**. GIF's bewegen alleen tijdens de actieve afspeelbeurt in de speler, niet eindeloos in elke bibliotheekkaart. Bij stop of einde wordt het actieve beeld vervangen.

Niet alle videocodecs in een MP4 kunnen door iedere browser worden afgespeeld. Dan kan de geluidsroute nog wel werken terwijl de video niet getoond wordt. De server gebruikt HTTP Range voor efficiënt seeken in MP4.

## 8. Logs en foutdiagnose

Open de logmap:

```powershell
.\Open_Logboeken.bat
```

- `audit.jsonl` registreert import, afspelen, stoppen, wijzigingen aan groepen en instellingen, en previews.
- `software.jsonl` bewaart Python-fouten met tracebacks en nu ook browserfouten met een JavaScript-stack.
- `crashes.txt` is voor fouten tijdens onverwacht afsluiten.

De waveform-meting bewaart geen spraak. Browseraudio blijft lokaal. Het bronbestand wordt bij verwijderen uit de bibliotheek niet van de schijf verwijderd.

## 9. Als een bestand ontbreekt of geblokkeerd wordt

Controleer:

```powershell
Get-ChildItem .\app\webinterface\statisch
```

Je moet minstens `dashboard.html`, `dashboard.js` en `stijl.css` zien. Als Windows-beveiliging iets in quarantaine heeft geplaatst, onderzoek de detectie en ga niet over op het uitschakelen van beveiliging. De lokale webserver logt bij ontbrekende bestanden de volledige Python-traceback.

## Nog te doen

De huidige editor kiest een virtueel fragment met begin- en eindmarkering. Exporteren naar een nieuw, fysiek ingekort bestand, automatisch volume normaliseren, gelijktijdig meerdere effecten met een eigen volumemixer en de zelfstandig installeerbare Windows EXE zijn nog aparte ontwikkelstappen.
