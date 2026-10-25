# DrostSoundboard 5.4: gedetailleerde golfvorm en previewpositie

Deze update verandert de **fragmenteditor en de visuele piekweergave**. Je Razer-microfoon, de live audiomixer, VB-CABLE, je database, 15 favorieten en groepen blijven hetzelfde.

## 1. Installeren op je bestaande Windows-computer

Sluit DrostSoundboard en alle open dashboardtabbladen voordat je bestanden vervangt. Open PowerShell en voer uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests -DestinationPath .\DrostSoundboard_backup_voor_fase54.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase5_4_Editor_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard

.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Verwacht **208 tests** en `OK`. Er zijn geen nieuwe Python-afhankelijkheden nodig. Bij een antivirusdetectie: onderzoek de melding. Schakel je beveiliging niet uit en maak geen uitzondering voor het project.

Start daarna de applicatie:

```powershell
.\Start_DrostSoundboard.bat
```

Ververs de browser met `Ctrl + Shift + R` als je nog de oude golfvorm ziet.

## 2. De editor gebruiken

1. Open je bibliotheek, kies een geluid en klik op de bewerkknop. Na het toevoegen van één geluid opent de editor automatisch.
2. Kies met de twee trimhandvatten of met **Begin** en **Duur** het fragment. Maximaal 120 seconden, of de resterende bronlengte als die korter is.
3. De grotere golfvorm toont gemeten pieken en het gemiddelde niveau in hetzelfde tijdvak. De golfvorm is visueel genormaliseerd en is **niet** hetzelfde als een dBFS-meter.
4. Klik ergens op de golfvorm. De verticale witte lijn is de afspeelpositie. Sleep die lijn met de muis om de positie te wijzigen.
5. Druk op **Spatie** om af te spelen of te pauzeren. Als de cursor of de editor achtergrond focus heeft, werkt de sneltoets; tijdens typen in invoervelden wordt hij niet uitgevoerd.
6. Gebruik **Links/Rechts** als de afspeelcursor focus heeft om 0,1 seconde nauwkeurig te zoeken. Met **Shift** wordt dat 1 seconde. **Home/End** verplaatsen naar begin of einde van de selectie.
7. Klik **Stop** om de preview af te sluiten en de cursor terug naar het begin van je selectie te zetten.
8. Klik **Wijzigingen opslaan** om de gekozen begin- en eindpositie in SQLite te bewaren. Het originele audio- of videobestand blijft ongewijzigd.

De afspeelcursor volgt het echte `currentTime`-veld van de browsermedia. Hij wordt niet met een verzonnen tijdincrement bijgewerkt. Een MP4-beeld gebruikt dezelfde browsermedia om synchronisatie te bewaren. Het beluisteren in de editor loopt **niet** via de VB-CABLE-mixer.

## 3. Piekwaarde

De samplepiek van de twee audiometers blijft maximaal **1,2 seconde** in de tekst staan. De RMS-balk en het witte RMS-eindstreepje blijven direct en afzonderlijk reageren. Een achtergrondruisniveau lager dan de zichtbare dBFS-schaal laat geen nieuwe vasthoudpiek ontstaan.

## 4. Techniek en logging

* In `app/audio/bronduur_en_golfvorm.py` verwerkt Python het geselecteerde tijdvak in blokken. Alleen maximaal 1200 kolommen met piek- en RMS-samenvattingen gaan naar de browser.
* `app/webinterface/lokale_webserver.py` accepteert via de bestaande golfvormroute de optionele parameter `resolutie`. De server weigert te hoge waarden en bewaart geen audiosamples.
* In `app/webinterface/statisch/dashboard.js` staan losse functies voor tijdselectie, cursorpositie, afspelen, pauzeren, scrubben, de golfvorm en de visuele piek.
* De bestaande auditlog registreert `preview_gestart`, `preview_gestopt` en `preview_verplaatst`. De werkelijke audiomixer wordt daarvoor niet aangeroepen.
* Browserfouten worden via `/api/frontendfout` met hun JavaScript-stack geregistreerd in `software.jsonl`.

## 5. Als iets niet werkt

Als de browser geen preview laat horen, controleer dan eerst of je Windows-uitvoer naar de Razer staat, het tabblad niet gedempt is en de MP3/MP4-codec door de browser wordt ondersteund. Test met een korte MP3 of WAV. Open bij een fout:

```powershell
.\Open_Logboeken.bat
```

Controleer `software.jsonl` op de oorspronkelijke fout en stacktrace. De automatische tests hebben niet op jouw specifieke Razer en VB-CABLE gedraaid. De audiomixer is niet gewijzigd.
