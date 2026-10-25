# DrostSoundboard 5.6.1: MP4 downloaden met beeld én geluid

In versie 5.6 werd bij MP4-export de audio onbedoeld weggelaten door een
bewuste, maar achteraf verkeerde ontwerpkeuze. Versie 5.6.1 corrigeert dit.

## Wat verandert er?

- **Download als MP4:** bevat voortaan H.264-videobeeld én AAC-audio.
- Als je geluidsbron zelf een MP4 is, knippen we video en audio samen.
- Als je MP3 of WAV een gekoppelde GIF heeft, loopt de GIF door zolang het
  geselecteerde geluidsfragment duurt. De geselecteerde audio wordt toegevoegd.
- De maximale fragmentduur is ook in de MP4-export **120 seconden**.
- **Download als MP3:** alleen audio, zoals voorheen.
- **Download als GIF:** alleen animatie. GIF ondersteunt geen ingebouwd geluid.
- De download gebruikt de **huidige selectie in de editor** of de opgeslagen
  begin- en eindtijden vanuit de bibliotheek.
- De originele bestanden, favorieten, groepen en audiomixer blijven onaangetast.

Een MP4 is geen kopie zonder meer. We coderen video opnieuw als H.264 en geluid
als AAC. Dat maakt afspelen in gangbare spelers eenvoudiger en knippen op de
gekozen positie mogelijk, maar kan een kleine afwijking opleveren aan de
randen door compressie en framing. Export kan tijdelijk CPU gebruiken.

## Installeren op je bestaande Windows-project

Sluit DrostSoundboard volledig, inclusief het PowerShell-venster waarin
Python draait. Download `DrostSoundboard_5_6_1_MP4_met_geluid_Update.zip` naar
je Downloads-map.

Voer in PowerShell de volgende opdrachten uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_561.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_5_6_1_MP4_met_geluid_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard

.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

De gecontroleerde versie heeft **237 tests** met als eindresultaat `OK`.
Enkele tests gebruiken expres een ongeldig MP3-bestand. Daardoor kunnen
meldingen over een ongeldige MPEG-header zichtbaar zijn; die melding op
zich is geen fout in de MP4-export.

Start vervolgens zonder argumenten:

```powershell
.\Start_DrostSoundboard.bat
```

Ververs de browser met `Ctrl + Shift + R`.

## Controleren

1. Open **Bibliotheek beheren**, kies een bestaand geluid met MP4-video en
   klik op **Download > MP4**.
2. Open de *nieuw gedownloade* MP4 in een gewone videospeler. Je moet beeld
   én geluid horen. Eerder gedownloade MP4's blijven stil; die veranderen niet.
3. Open een MP3 of WAV waaraan je een GIF hebt gekoppeld. Download als MP4
   en controleer of de animatie zichtbaar is en het geluid tegelijk afspeelt.
4. Open de editor. Kies bijvoorbeeld seconde 5 tot 12,5 en download opnieuw
   als MP4. Het nieuwe filmpje hoort ongeveer 7,5 seconden te duren, en
   geluid en beeld beginnen bij de gekozen knipselectie.
5. Controleer desgewenst de auditregel `los_mediaformaat_geexporteerd` in
   `%LOCALAPPDATA%\DrostSoundboard\logboeken\audit.jsonl`.
   Problemen staan met traceback in `software.jsonl`.

Je hoeft Python of FFmpeg niet opnieuw te installeren. De bestaande
`imageio-ffmpeg`-afhankelijkheid levert de benodigde converter.

Als antivirussoftware onderdelen blokkeert, onderzoek de detectie eerst.
Schakel Windows-beveiliging niet uit en voeg niet zomaar een uitzondering toe.
