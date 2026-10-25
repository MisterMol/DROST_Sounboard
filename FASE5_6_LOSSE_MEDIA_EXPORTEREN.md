# DrostSoundboard 5.6.1: losse bestanden downloaden (MP4 inclusief geluid)

Deze versie bouwt verder op versie 5.5. De bestaande audiomixer, Windows-apparaten,
Razer-microfoon, VB-CABLE, favorieten, groepen en bibliotheek veranderen niet.

## Wat kun je nu?

Open **Bibliotheek beheren** en gebruik bij een regel de knop **Download**.
Je kunt hetzelfde venster openen vanuit **Geluid bewerken** via **Download als…**.

* **MP3** bevat alleen het audiofragment tussen de geselecteerde begin- en eindtijd.
  Het formaat is 192 kbit/s MP3, stereo 48 kHz. De volume-instelling van
  DrostSoundboard geldt voor het afspelen in gesprekken en wordt niet gebruikt
  om de oorspronkelijke audiokwaliteit bij een export zachter te maken.
* **MP4** bevat videobeeld én het bijbehorende geselecteerde audiofragment.
  Bij een oorspronkelijke MP4 worden beide sporen samen geknipt en als H.264
  video met AAC-audio opgeslagen. Wanneer een geluid alleen een gekoppelde
  GIF als beeld heeft, wordt de animatie herhaald en met de bijbehorende
  MP3/WAV-audio gecombineerd tot maximaal twee minuten.
* **GIF** is exact de gekoppelde GIF, zonder verandering van de inhoud.
  Als geen GIF is gekoppeld maar het bronbestand een MP4 is, maakt de app
  er een GIF van. Voor een hanteerbaar bestand gebruikt deze conversie
  maximaal 12 seconden, 10 beelden per seconde en maximaal 480 pixels breed.

Bij een geluidsbestand zonder video of gekoppelde GIF zijn de MP4- en GIF-
knoppen uitgeschakeld. Een MP4-videobestand kan wel apart worden omgezet
naar een MP3 en een GIF.

Voor de webbibliotheek gelden de opgeslagen knippunten. Vanuit de editor
wordt juist de zichtbare selectie gebruikt, zelfs als je die nog niet hebt
opgeslagen. De export schrijft nooit het oorspronkelijke bronbestand over.

## Installeren

1. Sluit de huidige DrostSoundboard en het bijbehorende PowerShell-venster.
2. Download `DrostSoundboard_5_6_1_MP4_met_geluid_Update.zip` naar Downloads.
3. Voer deze opdrachten in PowerShell uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_561.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_5_6_1_MP4_met_geluid_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard

.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

De verwachte testuitkomst is **237 tests, OK**. Er zijn geen nieuwe
Python-pakketten nodig, want versie 5.5 gebruikt al `imageio-ffmpeg`.

Start daarna met:

```powershell
.\Start_DrostSoundboard.bat
```

Ververs de webpagina met `Ctrl + Shift + R` om het nieuwe JavaScript en CSS
te laden.

## Zelf controleren

1. Open Bibliotheek beheren. Bij een bestaande MP3 zie je Download.
2. Klik op Download. Kies MP3. Open het gedownloade bestand in Windows.
3. Open een geluid met MP4-video. Exporteer MP4 en controleer dat zowel
   het beeld als het geluid te horen is. Exporteer MP3 om alleen geluid te bewaren.
4. Koppel een GIF aan een geluid. Download het als GIF en controleer dat
   de animatie blijft werken. Kies MP4 en controleer dat je de GIF én
   het bijbehorende geluid tegelijk kunt afspelen.
5. Open de fragmenteditor. Selecteer een kort fragment, bijvoorbeeld
   1.250 tot 3.750 seconden. Klik op Download als… en kies MP3. Het resultaat
   moet alleen de geselecteerde 2,5 seconden bevatten.
6. Controleer `audit.jsonl` op `los_mediaformaat_geexporteerd` en bij fouten
   `software.jsonl` op de volledige traceback.

## Beperkingen en aandachtspunten

Een GIF heeft zelf geen audiospoor. Bij het exporteren als MP4 voegt
DrostSoundboard daarom de audio van het gekoppelde geluidsbestand toe.
Een gewone GIF-export blijft zonder geluid: dat is een beperking van GIF zelf.

MP3 is een gecomprimeerd formaat. Een export wordt opnieuw gecodeerd, dus
voor milliseconde-nauwkeurige montage blijft ongecomprimeerde audio de beste
technische bron. De kniptijden worden tot op de gebruikelijke fragmentprecisie
bewaard, maar MP3-decoders kunnen een kleine vertraging door encoderpadding
hebben. Een video wordt opnieuw gecodeerd om nauwkeurig bij de selectie te
beginnen in plaats van op de vorige videokeyframe.

FFmpeg mag maximaal één losse export tegelijk uitvoeren. Dat beperkt
onnodige belasting tijdens het gamen. Een lange MP4-conversie gebruikt wel
CPU; doe zo'n conversie bij voorkeur niet tijdens een belangrijke call.

Downloads lopen uitsluitend via de lokale server en het beveiligde POST-
endpoint. De bestanden worden als tijdelijke uitvoer gemaakt en na het
terugsturen verwijderd. De bestaande media en database blijven intact.

Wanneer Windows-beveiliging een bestand blokkeert, laat de detectie eerst
onderzoeken. Schakel de beveiliging niet uit en voeg niet zomaar een
uitzondering toe.
