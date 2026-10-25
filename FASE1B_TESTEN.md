# Fase 1B: je eigen WAV-bestand afspelen via VB-CABLE

**Stand van zaken op 23 oktober 2026:** de vorige kabeltest is op je Windows-pc geslaagd. Je hebt de Razer als normale microfoon en luidspreker, en de 440 Hz-test kwam terug via CABLE Output. In deze stap laten we een echt audiobestand door dezelfde virtuele kabel gaan.

**Dit is nog geen volledige soundboard-app.** Het kleine venster is alleen een praktische test om de audiolaag te controleren. Het uiteindelijke dashboard bouwen we later in HTML, CSS en JavaScript. De nieuwe audiomodules worden daarbij hergebruikt.

## Stap 1. Update uitpakken

Open PowerShell:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase1B_Update.zip" -DestinationPath . -Force
cd .\DrostSoundboard
```

De update-ZIP bevat de map `DrostSoundboard` zelf. Gebruik dus **niet** je projectmap als bestemming bij `Expand-Archive`, anders krijg je een dubbele map. Als je zelf gewijzigde bestanden hebt gemaakt, maak daar eerst een kopie van. Je bestaande `.venv` en logboeken blijven staan.

## Stap 2. Eén extra Python-onderdeel installeren

De audioconversie gebruikt nu `numpy`. Voer opnieuw het bestaande installatiescript uit:

```powershell
.\Installeer_ontwikkelomgeving.bat
```

Dit script maakt je project niet opnieuw aan. Het controleert de bestaande omgeving en installeert alleen wat uit `requirements.txt` ontbreekt. Als dit mislukt, bekijk dan `installatie.txt` in de logmap.

## Stap 3. Automatische tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Verwachte einduitvoer van deze update: `Ran 45 tests` en `OK`. Deze 45 tests zijn gecontroleerd met gesimuleerde audioapparaten. De echte WAV-uitvoer op jouw Windows-pc moet nog getest worden.

## Stap 4. Open het eenvoudige testvenster

```powershell
.\Speel_Eigen_Geluid.bat
```

Er verschijnt een klein venster met **Kies WAV**, **Afspelen**, **Stop** en **Sluiten**. Het voorbeeldbestand `voorbeeld_ping.wav` is al geselecteerd. Klik dus eerst op **Afspelen**, zonder een eigen bestand te hoeven zoeken.

Bij het spelen worden de gewone `CABLE Input` en `CABLE Output` opnieuw opgezocht met Windows WASAPI. We veranderen geen Windows-standaardinstellingen en we openen je Razer-microfoon niet.

**Belangrijk:** je hoort het geluid normaal gesproken niet via je Razer-headset. Het gaat direct naar VB-CABLE, zodat een Windows-app die CABLE Output opneemt het kan ontvangen. Omdat fase 1A de kabel al heeft gemeten, is deze stap bedoeld om het afspelen van echte bestanden te testen. Test dit liever niet tijdens een gesprek als de belapp al CABLE Output gebruikt.

## Stap 5. Zelf een WAV kiezen en stoppen

Klik op **Kies WAV** en selecteer je eigen korte WAV. Voor deze fase ondersteunt de lezer **ongecomprimeerde PCM WAV**, mono of stereo, 8, 16, 24 of 32 bit, maximaal 45 seconden en maximaal 40 MiB. Veel WAV's van 44.100 Hz worden automatisch naar 48.000 Hz omgezet.

MP3, M4A, MP4 en WAV met een niet-PCM-encoding zijn nog niet ondersteund. Die komen met de bibliotheekimport in een latere fase. Python 3.13 leest PCM WAV met de standaardbibliotheek `wave`; dit is een bewust eenvoudige eerste stap.

Wil je de knop **Stop** testen? Kies in de map `voorbeelden` het bestand `voorbeeld_lang_8seconden.wav`. Klik op **Afspelen** en daarna, voordat de acht seconden voorbij zijn, op **Stop**. Dit moet worden geregistreerd als `handmatig_gestopt`.

## Stap 6. Controleer de audit

Open de logmap:

```powershell
.\Open_Logboeken.bat
```

Of bekijk de laatste auditregels in PowerShell:

```powershell
Get-Content "$env:LOCALAPPDATA\DrostSoundboard\logboeken\audit.jsonl" -Tail 12
```

Voor een geslaagde speelactie zie je onder meer:

- `afspeelverzoek_ontvangen`
- `geluid_gestart`, met de bestandsnaam, volume en beoogde duur
- `geluid_gestopt`, met stopreden, hoeveelheid aangeleverde audio, verstreken tijd en bufferproblemen
- `afspeelverzoek_afgerond`

Bij een fout krijg je `afspeelverzoek_mislukt` in het auditlog en de **volledige Python-traceback** in `software.jsonl`.

Een auditregel `volledig_aangeleverd` betekent dat de audiodata zonder driverfout aan de kabel is aangeboden. Het bewijst niet dat iemand in Discord het geluid daadwerkelijk heeft gehoord.

## Als het fout gaat

| Melding | Betekenis of eerstvolgende controle |
| --- | --- |
| `ModuleNotFoundError: numpy` | Draai `Installeer_ontwikkelomgeving.bat` opnieuw. |
| `GELUID-003` | Je hebt geen WAV gekozen. Voor MP3 volgt later importconversie. |
| `GELUID-013` | Het bestand heeft meer dan twee kanalen. Kies een mono- of stereobestand. |
| `GELUID-017` | Het fragment is langer dan 45 seconden. Gebruik een korter testfragment. |
| `GELUID-019` | Het bestand is beschadigd, niet leesbaar of geen ondersteunde PCM WAV. |
| `AFSPELEN-002` | Om verkeerd routen te voorkomen is een ander uitvoerapparaat dan CABLE Input geweigerd. |
| `PortAudioError` | Een audioapparaat of 48.000 Hz kon niet worden geopend. Kijk in het softwarelog voor apparaatnummer en originele traceback. |

## Wat stuur je terug?

Stuur het resultaat van **stap 3** en vertel wat het kleine venster laat zien na **Afspelen** en **Stop**. Bij fouten mag je de meest recente foutregel uit `software.jsonl` sturen. Kijk eerst of daar privépaden in staan.

**Hierna volgt fase 2:** de Razer-microfoon toevoegen aan een continue mix, dan de drie standen `Verbonden met soundboard`, `Verbonden zonder effecten` en `Verbinding verbroken`. Het HTML-dashboard volgt na een stabiele audioverbinding.
