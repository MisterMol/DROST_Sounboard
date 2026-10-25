# DrostSoundboard: fase 2.2, automatisch herstel bij verbinden

**Datum:** 23 oktober 2026  
**Doel:** Eén keer op **Verbinden** klikken moet genoeg zijn, ook als Windows de eerste poging tijdelijk weigert. Het uitzetten van geluidseffecten mag de microfoon niet uitschakelen.

## Waarom deze wijziging nodig is

Op de Windows-computer van de gebruiker ontstond in de gecombineerde WASAPI-stream een herhaalde PortAudio-fout tijdens `audiostroom.start()`:

```text
PaErrorCode -9999
WdmSyncIoctl: DeviceIoControl GLE = 0x00000006
```

De afzonderlijke Razer-microfoontest werkte. De aparte VB-CABLE-test werkte eerder ook. Bij de vijfde verbindingspoging begon de live-mixer wel te werken. Vervolgens konden WAV-geluiden worden afgespeeld en gestopt, terwijl er geen bufferproblemen werden gemeld.

**Een WAV-bestand kiezen veroorzaakt de oplossing niet.** De functie voor verbinden leest het geselecteerde WAV-bestand niet. De latere succesvolle start kwam na meerdere pogingen. Wat de tijdelijke driverfout precies veroorzaakt, is niet bewezen.

## Wat is in deze versie gewijzigd?

* De audiowerkdraad maakt vóór de WASAPI-aanroepen Windows COM beschikbaar en ruimt zijn eigen COM-initialisatie na afloop op. Windows schrijft COM-initialisatie voor bij de IAudioClient-interface.
* Een **specifieke** WdmSyncIoctl-fout met `GLE = 0x00000006` krijgt maximaal vijf nieuwe pogingen, dus zes in totaal.
* Tussen pogingen wordt de mislukte audiostream eerst gestopt indien actief en daarna gesloten. Als dit afsluiten mislukt, worden er niet zomaar meer pogingen gedaan.
* Het venster toont bij verbinden welk pogingnummer actief is. De verbinding wordt pas groen zodra de stream daadwerkelijk gestart is.
* Iedere herstelbare fout wordt met de **originele volledige traceback** in `software.jsonl` bewaard. Bij herstel komt bovendien een auditgebeurtenis in `audit.jsonl`.
* Niet-herkende driverfouten en verkeerde parameters leiden meteen tot een foutmelding en worden niet eindeloos herhaald.
* Het gekozen WAV-bestand is geen voorwaarde om de microfoon te verbinden.

Deze verbetering maakt de app robuuster bij de **aangetroffen** fout, maar kan niet garanderen dat ieder driverprobleem automatisch herstelbaar is. Als alle zes pogingen mislukken, blijft de originele driverfout zichtbaar.

## Zo installeer je de update

Sluit DrostSoundboard volledig. Open PowerShell en voer deze opdrachten uit.

### Stap 1. Ga naar je projecten

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"
```

### Stap 2. Maak een broncodeback-up

```powershell
Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.py,.\DrostSoundboard\*.bat,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_audioherstel.zip -Force
```

### Stap 3. Pak de update uit

Download `DrostSoundboard_Fase2_Audioherstel_Update.zip` naar Downloads.

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase2_Audioherstel_Update.zip" -DestinationPath . -Force
cd .\DrostSoundboard
```

Je `.venv`, eigen geluidsbestanden en logboeken blijven behouden. Deze update vereist geen nieuwe Python-pakketten.

### Stap 4. Controleer de tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Verwacht: minimaal 89 tests en `OK`.

### Stap 5. Start de app en test opnieuw

```powershell
.\Start_DrostSoundboard.bat
```

1. Laat **Soundboard aan** nog uit staan en klik meteen op **Verbinden**. Het is niet nodig eerst een WAV-bestand te kiezen.
2. Praat duidelijk in je Razer-microfoon en controleer of de microfoonmeter zichtbaar reageert. Het niveau bij stille kamer kan heel laag zijn, bijvoorbeeld rond min 70 dBFS. Dat is niet hetzelfde als een defecte microfoon.
3. Bekijk in `mmsys.cpl` onder **Opnemen** of de meter van **CABLE Output** tijdens het praten beweegt.
4. Vink **Soundboard aan** aan, klik op **Geluid afspelen**, controleer of de uitvoermeter beweegt en klik op **Stop geluid**.
5. Vink **Soundboard aan** uit. Praat opnieuw. Je stem moet via CABLE Output blijven doorlopen.
6. Klik op **Verbinding verbreken** en controleer of de status op **Niet verbonden** komt.

Test bij voorkeur zonder lopend Discord- of WhatsApp-gesprek. Verander je standaard Windows-microfoon niet voor deze test.

## Waar vind ik de herstelpogingen terug?

Open de logmap met:

```powershell
.\Open_Logboeken.bat
```

Zoek in `software.jsonl` op:

| Gebeurtenis | Betekenis |
| --- | --- |
| `windows_com_voor_audio_voorbereid` | COM is klaargezet op de audiowerkdraad |
| `tijdelijke_audio_startfout` | Een bekende WDM-fout, met traceback en pogingnummer |
| `audio_start_automatisch_hersteld` | Na één of meer mislukte pogingen werkte de stream alsnog |
| `live_audioverbinding_mislukt` | Alle pogingen zijn mislukt, of er was een andere fout |
| `live_signaalmeting` | De gemeten signaalniveaus en callbacktellers |

In `audit.jsonl` staan `verbinding_aangevraagd`, `audio_start_automatisch_hersteld` (indien nodig), `verbinding_gestart` en `verbinding_verbroken`. Verder worden het starten en stoppen van afzonderlijke WAV-geluiden bewaard. Geen ruwe microfoonopnames.

## Als het nog niet werkt

Als de bekende WDM-fout bij elke start opnieuw optreedt, is de volgende technische stap het vervangen van de gecombineerde `sounddevice.Stream` door een aparte `InputStream` en `OutputStream` met een begrensde audiobuffer. Daarmee kunnen de Razer en VB-CABLE onafhankelijk starten. Hiervoor moeten we ook een oplossing bouwen voor verschillen tussen de audioklokken.

Stuur voor die vervolgstap het nieuwste `software.jsonl`, het nieuwste `audit.jsonl` en de status van de twee meters. Ga niet zomaar drivers verwijderen of Windows-apparaten uitschakelen.
