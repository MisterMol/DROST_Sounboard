# DrostSoundboard 5.7: snelle bibliotheek en overzichtelijk beheer

Dit is een gerichte update over DrostSoundboard 5.6.1. De bestaande VB-CABLE-verbinding, favorieten, groepen en geluidsbestanden blijven behouden.

## Wat is nieuw?

* **Preview** staat als gewone knop bij elk bibliotheekgeluid, ook als het geen favoriet is. Je kunt offline, zonder verbonden microfoon, lokaal luisteren. Het volledige **ingestelde fragment** wordt afgespeeld, dus met de opgeslagen begin- en eindselectie en maximaal twee minuten.
* Dezelfde Preview-knop wordt tijdens het spelen een **rode Stop-knop**. Na stoppen of wanneer het geluid is afgelopen, staat er weer Preview. Stop laat de microfoonverbinding ongemoeid.
* De **drie puntjes** openen een klein menu. Bovenaan staat **Bewerken**; verder **Afspelen in gesprek**, **Preview** en alleen de daadwerkelijk beschikbare downloads: MP3, MP4 met audio, losse afbeelding of GIF.
* **Afspelen in gesprek** werkt ook zonder dat het geluid een favoriet is. Hiervoor moet DrostSoundboard verbonden zijn en moeten geluidseffecten aan staan. Als de live audiostream stopt, verandert de knop weer terug.
* Nieuwe geluiden krijgen standaard **100% volume**. In de editor kun je kiezen tussen **0% en 200%**. Bestaande individuele instellingen blijven staan; bij een selectie in **Bibliotheek beheren** is er een knop **Selectie op 100%**.
* In het grote beheer kun je zoeken op naam, bestandsnaam, beschrijving, uitgesproken tekst, zoekwoorden en groep; filteren op groep en bestandsformaat; sorteren op naam of fragmentduur; en grotere aantallen stapsgewijs tonen.
* In het grote beheer zijn ook Preview, Bewerken en het actiemenu per regel beschikbaar, plus bulkexport als ZIP, groepskoppeling en verwijderen uit de bibliotheek.
* Overbodige footer- en instructieteksten zijn weggehaald, zodat de bibliotheek de beschikbare ruimte benut.

## Waarom 200% soms minder hard lijkt

100% geeft de oorspronkelijke digitale amplitude terug. Boven 100% worden audiosamples versterkt **als er digitale ruimte over is**. Wanneer een origineel al bijna 0 dBFS bereikt, zou harder vermenigvuldigen scherpe vervorming geven. De voorbereiding begrenst de volledige golfvorm daarom als dat nodig is. De boost is een **gevraagde versterking**, geen garantie op twee keer zoveel hoorbare luidheid. Het gewone browser-audio-element kan previews niet verder dan 100% versterken; de waarde tot 200% geldt voor de live audiomixer.

## Update installeren op Windows 11

Sluit eerst de DrostSoundboard-browserpagina én het terminalvenster waarin de audiomixer draait. Zorg dat het update-ZIP-bestand in `Downloads` staat.

Open PowerShell en plak:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_57.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_5_7_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard

.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Verwacht onderaan: `Ran 247 tests` en `OK`. Meldingen over foutieve MPEG-headers zijn in de tests van opzettelijk beschadigde MP3's geen testfout.

Start daarna:

```powershell
.\Start_DrostSoundboard.bat
```

Druk in de browser op `Ctrl + Shift + R` voor de nieuwe JavaScript en CSS.

**Let op:** als Windows-beveiliging een script of het ZIP-bestand blokkeert, schakel Defender niet uit. Onderzoek eerst de bedreigingsnaam onder Windows-beveiliging > Beveiligingsgeschiedenis.

## Controle in vijf minuten

1. Kies een geluid in de rechter bibliotheek en klik op **Preview**. Controleer dat de knop rood **■ Stop** wordt en dat je het geluid alleen via je eigen geluidsuitvoer hoort. Klik op Stop. Na het einde van het fragment hoort er weer Preview te staan.
2. Klik op **···** naast een gewone MP3. Je ziet Bewerken, Afspelen in gesprek, Preview en MP3. Je ziet daar **geen** MP4, GIF of afbeelding als die niet bestaan.
3. Klik op **···** bij een MP4 of een geluid met een gekoppelde GIF of afbeelding. Controleer dat alleen voor dat geluid toepasselijke mediaformaten verschijnen. Een MP4-download bevat video **én** geluid.
4. Open **Bibliotheek beheren**. Filter op je groep South Park, sorteer op fragmentduur en zoek op een woord uit een beschrijving. Kies een geluid om het direct lokaal af te spelen; bewerk er één en keer daarna terug naar dezelfde beheerpagina.
5. Voeg een nieuw geluid toe. Controleer dat het volume standaard 100% is. Zet het op 150%, sla op en heropen het. Selecteer vervolgens geluiden in Beheren, klik op **Selectie op 100%** en bevestig. Het originele mediabestand en de knipgrenzen blijven onaangetast.

## Logging en privacy

Audio-effecten die naar gesprekken gaan gebruiken de bestaande gelogde audioacties. Previews en downloads gebruiken bestaande auditgebeurtenissen. De bulkactie registreert `meerdere_geluidsvolumes_gewijzigd`. Tracebacks blijven in `%LOCALAPPDATA%\DrostSoundboard\logboeken\software.jsonl` beschikbaar. Gebruik `Open_Logboeken.bat` om de logmap te openen.

Geluidsbestanden staan op je eigen pc. Verwijderen uit de bibliotheek verwijdert de bronbestanden niet. De lokale webserver blijft alleen via `127.0.0.1` toegankelijk. De echte Razer-, AirPods- en VB-CABLE-hardware moet op jouw Windows-pc worden getest; de hier uitgevoerde tests zijn simulaties en lokale API-controles.
