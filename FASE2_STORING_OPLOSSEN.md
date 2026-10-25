# Fase 2: waarom hoor ik geen geluid?

De eerdere fase 1-test heeft op jouw pc bevestigd dat `CABLE Input` naar `CABLE Output` kan sturen. In fase 2 meldt DrostSoundboard in het venster wel `Verbonden`, maar daarmee weten we alleen dat PortAudio de stream heeft geopend. **De diagnose-update meet nu ook of er werkelijk samples worden verwerkt en hoeveel signaal er binnenkomt.**

## Eerst twee belangrijke begrippen

- **Soundboard aan** betekent dat een afspeelverzoek is toegestaan. Het start nog geen geluid. Klik daarna op **Geluid afspelen**.
- De app stuurt de mix naar VB-CABLE. Je hoort dat niet automatisch zelf in je Razer-headset. De Windows-niveaumeter van **CABLE Output** is voor deze test belangrijker dan wat jij op je hoofdtelefoon hoort.
- **CABLE Input** is de afspeelkant van de virtuele kabel. **CABLE Output** is de opnamekant die Discord later als microfoon krijgt.
- **Verbonden** betekent op dit moment nog niet dat Windows of Discord de aangeboden samples ontvangt. Onze nieuwe meters meten de Python-kant van de verbinding.

## Stap 1: installeer de diagnose-update zonder opnieuw te beginnen

Sluit DrostSoundboard af. Voer in PowerShell uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.py,.\DrostSoundboard\*.bat,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_diagnose.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase2_Diagnose_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard

.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Verwacht: `Ran 76 tests` gevolgd door `OK`. Deze tests simuleren audiostromen. Het zijn nog geen metingen van je werkelijke Razer-microfoon.

Geen nieuwe Python-bibliotheken nodig. Je `.venv` en bestaande logboeken blijven behouden. Deze update vervangt bestaande projectbestanden; daarom maken we eerst een broncodeback-up.

## Stap 2: meet de Razer zonder live mixer

Zorg dat DrostSoundboard niet meer verbonden is en sluit het live-mixervenster. Start daarna:

```powershell
.\Diagnoseer_Microfoon.bat
```

Druk op Enter als het programma dat vraagt en praat **vijf seconden duidelijk** in je Razer-microfoon. De test speelt niets af en bewaart geen spraak. Het programma toont `Hoogste RMS`, `Hoogste piek`, `Audioblokken ontvangen` en `Bufferproblemen`.

- `Hoogste RMS` vrijwel `0.000000`: geen meetbare input. Controleer de fysieke mute-knop, Razer Synapse, de Windows-microfoonrechten en het ingangsvolume.
- `Hoogste RMS` bijvoorbeeld groter dan `0.003`: Python heeft echt geluid ontvangen van de Razer. Dat bevestigt dat de losse microfoon in principe werkt.
- Een fout met `MIC-...`: gebruik `software.jsonl` om de oorspronkelijke traceback terug te vinden.

Deze drempels zijn diagnosehulpmiddelen, geen formele kalibratie en geen garantie voor spraakverstaanbaarheid.

## Stap 3: test microfoon en mix samen

Start DrostSoundboard opnieuw:

```powershell
.\Start_DrostSoundboard.bat
```

Klik op **Verbinden**. Laat **Soundboard aan** voorlopig uit. Praat in de Razer. Bekijk de twee nieuwe meters onder **Live signaalcontrole**:

1. `Geluid dat binnenkomt van je microfoon` meet wat de Python-callback van Razer krijgt.
2. `Geluid dat Python naar CABLE Input stuurt` meet wat Python probeert door te geven.

Bekijk ook de teller `Callbacks`. Die moet steeds hoger worden. Er komt nu om de vijf seconden een `live_signaalmeting` in `software.jsonl` met de werkelijke niveaus.

## Stap 4: test een geluidseffect

Vink **Soundboard aan** aan, klik op **Kies WAV** en selecteer het bestand `voorbeelden\voorbeeld_lang_8seconden.wav`. Klik daarna op **Geluid afspelen**.

De tweede meter zou tijdens het afspelen moeten bewegen, ook als je zelf even niets zegt. Klik tijdens de acht seconden op **Stop geluid**. De tweede meter kan weer terugvallen op het niveau van de microfoon; de verbinding moet actief blijven.

Open nu `mmsys.cpl`, tabblad **Opnemen**. De groene meter van **CABLE Output** hoort op hetzelfde moment uit te slaan. Het is niet nodig om je standaardapparaten te wijzigen.

## Wat betekent de uitslag?

| Directe microfoontest | Meter microfoon | Meter naar kabel | Betekenis | Vervolg |
|---|---|---|---|---|
| Stil | Stil | Stil bij praten | Fysieke microfoon levert niet aantoonbaar spraak aan Python | Controleer mute, invoergain, Razer-software en Windows-rechten |
| Goed | Stil | Stil bij praten | Direct opnemen werkt, maar niet in de live duplexstream | Stuur `software.jsonl` en `audit.jsonl`; volgende stap wordt een aparte input- en outputstream |
| Goed | Beweegt | Beweegt | Python maakt een mix en biedt die aan | Controleer Windows-meter bij CABLE Output; zo nodig aparte kabeldiagnose |
| Goed | Stil | Beweegt alleen bij WAV | Geluidseffecten werken intern, maar microfoon bereikt de live mix niet | Diagnose van Razer-kanalen en duplexstream |
| Onbekend | Niet gemeten | Niet gemeten | Er komen geen callbacks of het venster is niet verbonden | Kijk naar de foutcode `LIVE-018` en stuur de log door |

Als de Python-uitvoermeter wél beweegt en de Windows-meter van **CABLE Output** niet, bewijst dat alleen dat Python samples aanbiedt, **niet** dat de driver ze aflevert. Dan meten we de opnamekant van de kabel apart.

## Optioneel: zelf meeluisteren via de Razer

Dit is niet nodig voor de diagnose, maar kan helpen om het signaal kort te controleren.

1. Druk op Windows + R en voer `mmsys.cpl` in.
2. Open tabblad **Opnemen** en dubbelklik **CABLE Output**.
3. Ga naar **Luisteren** en zet **Naar dit apparaat luisteren** aan.
4. Kies bij **Afspelen via dit apparaat** je `Luidsprekers (Razer USB Sound Card)`.
5. Klik op Toepassen en speel kort een geluid af.
6. **Zet Luisteren direct weer uit**. Anders kun je je eigen stem terughoren en ontstaat er gemakkelijk echo.

Doe dit alleen met je headset als uitvoer. Zet niet ook je speakers hard, want dan kan je microfoon geluid opnieuw oppikken. Deze optie heeft bovendien extra vertraging.

## Logs

Open:

```powershell
.\Open_Logboeken.bat
```

In `%LOCALAPPDATA%\DrostSoundboard\logboeken` zijn twee bestanden belangrijk:

- `software.jsonl`: elke vijf seconden signaalsterktes en eventuele originele Python-tracebacks. Zoek op `live_signaalmeting`, `microfoonniveau_gemeten` en `LIVE-018`.
- `audit.jsonl`: momenten waarop de microfoontest, verbinding en geluidseffecten zijn gestart of gestopt.

De metingen bevatten alleen numerieke niveaus. De app slaat hierbij geen echte geluidsopname op.

## Nog niet opgelost met deze update

Dit is een **diagnose-update**, geen belofte dat de live-mixer al op iedere combinatie van USB-headset en VB-CABLE werkt. Als directe Razer-opname slaagt maar de gecombineerde duplexstream stil blijft, vervangen we die stream door aparte invoer- en uitvoerstromen met een buffer ertussen. Dat ontwerp vereist extra synchronisatie zodat verschillende audioklokken geen haperingen veroorzaken. We kiezen die oplossing pas als de metingen aantonen dat hij nodig is.
