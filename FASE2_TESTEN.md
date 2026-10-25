# Fase 2: microfoon + soundboard aan of uit

Dit is de volgende stap van **DrostSoundboard**. Je hebt op jouw Windows 11-pc al 45 tests en een WAV-afspeelbeurt van 8 seconden succesvol uitgevoerd. In fase 2 testen we de nieuwe live-audiomixer: je stem gaat naar VB-CABLE en je kiest zelf of geluidseffecten daar bovenop komen.

> **Belangrijk:** deze nieuwe live-mixer is geprogrammeerd en met gesimuleerde audioapparaten getest, maar is nog **niet** op jouw Razer/Windows-combinatie uitgevoerd. Fase 2 is een prototype, niet de definitieve app of installer voor iedere pc. Houd voorlopig Discord en WhatsApp op hun normale microfoon terwijl je de lokale Windows-test doet.

## Stap 1. Bewaar je bestaande project en installeer alleen de update

Sluit eventuele DrostSoundboard-vensters. Open PowerShell:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

# Bewaar eerst de huidige broncode, zonder de zware .venv-map.
Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.py,.\DrostSoundboard\*.bat,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_fase2.zip -Force

# Het ZIP-bestand bevat zelf de map DrostSoundboard.
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase2_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard
```

De back-up bevat je broncode en documentatie. Je bestaande `.venv` wordt niet gekopieerd en blijft ongemoeid bij de update.

## Stap 2. De code controleren

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Verwacht: `Ran 64 tests` en `OK`. Dit zijn unit-tests met nagebootste audioapparaten. Ze zeggen nog niets over de daadwerkelijke verbinding met jouw fysieke microfoon.

De bestaande afhankelijkheden zijn onveranderd: `sounddevice` en `numpy`. Normaal hoef je het installatiescript deze keer niet opnieuw te draaien. Krijg je `ModuleNotFoundError`, gebruik dan `Installeer_ontwikkelomgeving.bat` en bekijk de installatielog.

## Stap 3. Open het live-venster

```powershell
.\Start_DrostSoundboard.bat
```

Het venster bevat:

* Een microfoonkeuzelijst. Je Razer staat als voorkeur gekozen als Windows die vindt.
* **Verbinden** en **Verbinding verbreken**.
* **Soundboard aan**. Die optie staat na het verbinden aanvankelijk **uit**.
* **Kies WAV**, **Geluid afspelen**, **Stop geluid**.

**Er gebeurt nog niets met je microfoon totdat je op Verbinden klikt.** Deze app verandert Windows' standaardmicrofoon of standaardluidsprekers niet.

## Stap 4. Test eerst alleen je stem, zonder Discord

1. Houd je Razer-headset als normale standaard-uitvoer en microfoon ingesteld.
2. Controleer in het venster dat `Microfoon (Razer USB Sound Card)` is geselecteerd.
3. Klik op **Verbinden**.
4. Wacht op `Verbonden, alleen microfoon`. Staat er `Verbindingsfout`, kopieer dan de melding en de nieuwste regels uit `software.jsonl`. Verander nog geen Windows-instellingen.
5. Druk `Windows + R`, voer `mmsys.cpl` in, ga naar **Opnemen**.
6. Praat gewoon in de Razer. De groene niveaumeter bij **CABLE Output** moet meebewegen. Je fysieke Razer-microfoon mag ook uitslaan.
7. Praat een halve minuut door en kijk of de status verbonden blijft.

De audiomotor werkt nu als een doorgeefluik: de microfoon gaat naar VB-CABLE. Het soundboard staat uit en je hoort jezelf niet terug via je speakers. Dat is de bedoeling.

Als er helemaal geen meteruitslag bij CABLE Output is, stuur dan de foutmelding of nieuwe logregels door. Niveaumeters bewijzen alleen dat Windows signaal ziet, niet dat Discord het doorlaat.

## Stap 5. Zet het soundboard aan en test een geluid

1. Laat de verbinding **actief**.
2. Vink **Soundboard aan** aan.
3. Klik op **Geluid afspelen**. Het lange WAV-voorbeeld is al geselecteerd.
4. Kijk of de meter bij **CABLE Output** uitslaat. Spreek tegelijkertijd om de microfoonmix te testen.
5. Speel het lange geluid opnieuw, klik binnen ongeveer twee seconden op **Stop geluid**. De stem moet blijven werken.
6. Vink **Soundboard aan** weer uit. Zeg iets tegen de Razer-microfoon. CABLE Output moet blijven bewegen als je praat.
7. Klik pas daarna op **Verbinding verbreken**. De meter van CABLE Output hoort dan niet meer door jouw stem te bewegen.

Dat zijn de drie gewenste standen: alleen stem, stem met geluidjes en niet verbonden. **Verbinding verbreken is iets anders dan soundboard uitzetten.**

## Stap 6. Optioneel: controleren in Discord

Doe deze stap **pas na een geslaagde lokale meter-test** en bij voorkeur in een apart testgesprek.

1. Open Discord en ga naar **Gebruikersinstellingen**, **Spraak en video**.
2. Laat **Uitvoerapparaat** op je Razer USB Sound Card staan.
3. Kies bij **Invoerapparaat** `CABLE Output (VB-Audio Virtual Cable)`.
4. Houd in DrostSoundboard de verbinding actief. Test je stem in Discord en daarna een geluid. Discord kan muziek of effecten wegfilteren door ruisonderdrukking.
5. Als je stopt met DrostSoundboard, kies in Discord eerst opnieuw `Microfoon (Razer USB Sound Card)` voordat je **Verbinding verbreken** gebruikt. Daarmee voorkom je een onverwacht stille microfoon.

We wijzigen niet automatisch de instellingen van Discord of WhatsApp.

## Stap 7. Bekijk de logboeken

```powershell
.\Open_Logboeken.bat
```

Je vindt de logboeken onder:

```text
%LOCALAPPDATA%\DrostSoundboard\logboeken
```

Bij correct gebruik komen in `audit.jsonl` onder andere de gebeurtenissen `verbinding_aangevraagd`, `verbinding_gestart`, `soundboard_ingeschakeld`, `geluid_gestart`, `geluid_gestopt`, `soundboard_uitgeschakeld` en `verbinding_verbroken` terug. Daar staat per geluid ook de naam, de afspeelbeurt-ID, de aangeboden duur en de stopreden.

Bij een driverfout staat een `LIVE-...` foutcode in de melding en bevat `software.jsonl` de originele Python-traceback, het betrokken apparaat en de driverinstellingen. De app bewaart geen spraakopnamen of inhoud van gesprekken.

## Mogelijke problemen

| Wat je ziet | Betekenis | Wat je doet |
|---|---|---|
| `LIVE-003` | Microfoon weigert op 48 kHz zowel mono als stereo. | Kijk in `mmsys.cpl > Opnemen > Microfoon > Eigenschappen > Geavanceerd` naar het formaat. Verander pas iets als we weten wat de driver ondersteunt. |
| `Invalid device` of `Invalid sample rate` | WASAPI accepteert de combinatie van apparaten of audioformaat niet. | Bewaar `software.jsonl` zodat we een andere streamopzet of resampling kunnen bouwen. |
| `LIVE-015` | De stream is onverwacht gestopt. | Controleer USB-verbinding en microfoonrechten. Probeer na de fout pas opnieuw te verbinden. |
| `LIVE-016` | Fout tijdens het realtime mixen. | De oorspronkelijke callbackfout staat in `software.jsonl`. |
| Meter beweegt, Discord hoort niets | Discord heeft andere invoer geselecteerd of verwerkt het signaal. | Controleer Invoerapparaat en ruisonderdrukking in Discord. |
| Je hoort jezelf dubbel | Windows heeft waarschijnlijk `Luisteren naar dit apparaat` aanstaan. | Zet die optie uit bij de microfoon of CABLE Output. |
| Na Verbinding verbreken ben je stil in Discord | Discord staat nog op CABLE Output. | Kies de fysieke Razer opnieuw als invoer in Discord. |

## Wat nog niet af is

Dit is een **tijdelijk tkinter-venster**, nog niet het uiteindelijke HTML/CSS/JavaScript-dashboard. Deze fase gebruikt één WAV tegelijk, een eenvoudige piekbegrenzing en vereist voor de microfoonmix voorlopig 48 kHz. Driftcompensatie voor alle Bluetooth-apparaten, een verfijnde limiter, media-import, bibliotheek en echte Windows-installer komen later. Sommige Windows-audiocombinaties kunnen een duplexstream weigeren en vragen dan om een ontwerp met aparte invoer- en uitvoerstromen.

**Stuur als resultaat terug:** (1) of het live-venster opent, (2) of `Verbonden, alleen microfoon` verschijnt, (3) of de meter van CABLE Output op je stem reageert, (4) of de Stop-knop het geluid stopt terwijl je stem blijft doorgaan, en (5) eventuele nieuwe foutmeldingen uit `software.jsonl`.
