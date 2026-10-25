# Fase 2.4. MP3, WAV en een eigen geluidsbibliotheek testen

## Wat is al bewezen?

Op 23 oktober 2026 heeft de onafhankelijke `Meet_CABLE_Output.bat` op de echte Windows-computer een 660 Hz-toon van DrostSoundboard herkend. De hoogste RMS was 0,10439, de hoogste piek 0,14700 en er waren nul bufferproblemen. Hiermee is bewezen dat Python audio in `CABLE Input` kan aanbieden en dat die audio via `CABLE Output` als opnamebron terugkomt. Discord en WhatsApp moeten nog apart worden getest.

## Wat is nieuw?

- Kies meerdere MP3- en WAV-bestanden in een keer via **MP3/WAV toevoegen**.
- Geef ieder item een eigen naam via **Naam wijzigen**.
- Je bibliotheek blijft bestaan na het sluiten van de app. Hij staat in `%LOCALAPPDATA%\DrostSoundboard\bibliotheek.sqlite3`.
- Selecteer een item, zet **Soundboard aan** en gebruik **Geluid afspelen**.
- Gebruik **Begin bij seconde** om midden in een lang muzieknummmer te beginnen.
- Om het programma licht te houden, wordt **maximaal 45 seconden per klik** gedecodeerd en gespeeld. De rest van het nummer wordt dus niet afgespeeld. Voor volledig lange nummers komt later streaming.
- Je eigen muziek wordt niet automatisch gekopieerd. Verplaats je het MP3-bestand uit Downloads, dan moet je het opnieuw importeren of terugplaatsen.
- De Razer-microfoon, het huidige audiopad, de aan/uit-knop en bestaande auditlogs blijven werken.

## Installatie op deze pc

**1. Sluit DrostSoundboard helemaal af.** Zorg dat er geen actieve audiostream meer open staat.

**2. Maak een back-up van de bestaande projectbroncode:**

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"
Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.py,.\DrostSoundboard\*.bat,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_mp3.zip -Force
```

**3. Download `DrostSoundboard_Fase2_MP3_Update.zip` naar Downloads en pak uit:**

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase2_MP3_Update.zip" -DestinationPath . -Force
cd .\DrostSoundboard
```

Het updatepakket bevat bewust geen `.venv`, logs of privégeluiden.

**4. Installeer de twee extra Python-afhankelijkheden:**

```powershell
.\Installeer_ontwikkelomgeving.bat
```

De installer gebruikt `requirements.txt` en installeert `soundfile` voor MP3/WAV en `soxr` voor hoogwaardige omzetting naar 48 kHz. Er hoeft geen losse FFmpeg-installatie gedaan te worden. Controleer bij een fout `%LOCALAPPDATA%\DrostSoundboard\logboeken\installatie.txt`.

**5. Voer de tests uit:**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Verwacht minimaal **124 tests** en `OK`. De meeste hardwaretests gebruiken nepapparaten. Deze test bewijst niet dat Discord al werkt.

**6. Start de app zonder parameters:**

```powershell
.\Start_DrostSoundboard.bat
```

## MP3's uit Downloads toevoegen

1. Klik op **MP3/WAV toevoegen**.
2. De bestandenkiezer opent standaard Downloads. Kies bijvoorbeeld `discord-call-sound.mp3`, `het_sneeuwt.mp3` en `jacob_droom.mp3`. Houd Ctrl ingedrukt om meerdere bestanden te kiezen.
3. Klik op **Openen**. De bestanden verschijnen in **Mijn geluidsbibliotheek**.
4. Klik op een geluid, klik op **Naam wijzigen** en geef het bijvoorbeeld de naam `Discord oproep`.
5. Stel **Begin bij seconde** in op `0`. Bij langere nummers kun je bijvoorbeeld `45` invullen om 45 seconden vanaf dat punt te horen.
6. Klik op **Verbinden**. Controleer dat je beide live-meters ziet bewegen als je praat.
7. Zet **Soundboard aan** en klik op **Geluid afspelen**. Zodra het fragment is voorbereid stuurt Python het naar de virtuele kabel.
8. Gebruik **Stop geluid**. Je microfoon blijft doorgaan.
9. Test **Soundboard uit**. Je stem blijft doorgaan en er worden geen nieuwe effecten gespeeld.

**Let op:** DrostSoundboard laat het MP3-geluid niet vanzelf via je Razer-headset horen. Dit is bewust: het effect wordt aangeboden aan `CABLE Input`, zodat je belapp het op `CABLE Output` kan opnemen.

## Controleer of Discord het geluid doorgeeft

Nu VB-CABLE op je pc apart is getest, kan je ook Discord controleren:

1. Open Discord en ga naar **Gebruikersinstellingen > Spraak en video**.
2. Kies onder **Invoerapparaat** de opnamebron **CABLE Output (VB-Audio Virtual Cable)**.
3. Laat **Uitvoerapparaat** op je Razer-headset staan.
4. Kies **Spraakactiviteit** (niet Push-to-Talk) voor de eerste proef, of houd bij Push-to-Talk de toets ingedrukt.
5. Gebruik de **microfoontest** van Discord. Test achtereenvolgens je stem en één kort MP3-fragment.
6. Wanneer muziek wegvalt, test dan **ruisonderdrukking / Krisp uit**. Ook automatische ingangsgevoeligheid of andere spraakfilters kunnen effecten wegdrukken.
7. Test een echte gesprekspartner pas nadat de lokale microfoontest goed klinkt.

Maak de geluiden niet onnodig hard. Bij de huidige testversie gebruikt een geluid standaard 35% amplitude. Een individuele volumeschuif en veiligere limiter komen in een latere fase.

## Logging en privacy

- `audit.jsonl`: onder andere `geluid_toegevoegd_aan_bibliotheek`, `geluidsnaam_gewijzigd`, `geluid_voorbereiden_aangevraagd`, `geluid_gestart` en `geluid_gestopt`. Bij stoppen worden de werkelijk aangeboden seconden gelogd. Voor afspeelbeurten is er een unieke ID.
- `software.jsonl`: foutcode, functie, regelnummer, oorzaak en volledige originele traceback bij ongeldige MP3, verdwenen bestand of afspeelfout.
- Bibliotheek: alleen eigen naam en het bestaande bestandspad in SQLite, geen microfoonopname.
- Bronbestanden staan nog steeds in de door jou gekozen map. Uit een lijst halen wist nooit de eigen MP3.

Open de logmap met:

```powershell
.\Open_Logboeken.bat
```

## Beperkingen

Dit is nog het tijdelijke Tkinter-venster. Het grote dashboard met tegels, zoekfunctie, GIF/MP4 en afbeeldingen komt later. Langere nummers worden in fase 2.4 niet volledig doorgestuurd, maar als instelbaar fragment van maximaal 45 seconden. Volledig afspelen van lange muziek vereist een aparte streaming- en bufferlaag om de applicatie licht te houden.

De uiteindelijke Windows-installer (EXE, geen Python nodig op de doelcomputer) is nog niet gebouwd. De huidige `.bat`-bestanden zijn alleen bedoeld voor de ontwikkelomgeving.
