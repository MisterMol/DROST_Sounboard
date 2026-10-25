# DrostSoundboard: webdashboard installeren en testen

Deze handleiding is geschreven voor Windows 11 en Python 3.13. Je bestaande DrostSoundboard staat in `C:\Users\jelle\Desktop\pythonProjects\DrostSoundboard`. Op een andere pc kun je dezelfde stappen uitvoeren vanuit de eigen projectmap.

## Wat is er anders?

DrostSoundboard opent nu een lokale webpagina in je standaardbrowser. Python blijft op de achtergrond aanstaan en mengt je microfoon met de geluidseffecten via VB-CABLE. We gebruiken geen externe website en sturen geen bestanden naar een cloudserver. Het adres is standaard `http://127.0.0.1:8765/`. Als die poort al bezet is, kiest de app zelf een vrije lokale poort en opent het juiste adres.

De vijftien favorietplekken hebben nummers 1 tot en met 15. Bij een groot scherm zie je meer kaarten naast elkaar; op een klein scherm minder. Hun volgorde verandert niet. Je favorieten, geluidsnamen, startpunten, volumeniveaus en gekozen fragmentduur staan in je SQLite-bibliotheek onder `%LOCALAPPDATA%\DrostSoundboard\bibliotheek.sqlite3`.

Je kiest per geluid de begintijd, het volume en de maximale fragmentduur. Een fragment mag nooit langer dan 120 seconden zijn. Een MP3 die drie minuten duurt mag je wel importeren. Je speelt daar dan maximaal twee minuten uit af, eventueel vanaf een zelfgekozen startpunt.

## Stap 1. Eerst testen of Discord het bestaande geluid ontvangt

Dit kan nog vóór je de webupdate installeert. Sluit eventuele andere programma's die VB-CABLE gebruiken.

1. Open DrostSoundboard en klik op **Verbinden**. Kies je Razer-microfoon als audiobron.
2. Zet **Soundboard aan** en speel de controletoon of een kort WAV-bestand af.
3. Open Discord. Ga naar **Gebruikersinstellingen**, daarna **Spraak en video**.
4. Zet **Invoerapparaat** op **CABLE Output (VB-Audio Virtual Cable)**. Zet **Uitvoerapparaat** op **Luidsprekers (Razer USB Sound Card)**.
5. Kies **Spraakactiviteit**. Zet tijdens de muziekproef **Krisp** en eventueel andere spraakruisfilters uit.
6. Klik op **Let's Check** of **Microfoontest**. Praat eerst. Speel daarna het geluid. Je moet beide terughoren.
7. Bel vervolgens iemand die ermee instemt om mee te testen en vraag diegene of zowel je stem als het WAV- of MP3-fragment doorkomt. De ingebouwde microfoontest bewijst niet dat de andere partij het daadwerkelijk ontvangt.

Als de andere partij niets hoort, controleer dan binnen Discord of je invoerapparaat echt nog steeds CABLE Output is. Controleer ook het volume, de invoermodus, mute en ruisonderdrukking. Deze stappen zijn in lijn met de officiële uitleg van Discord: https://support.discord.com/hc/en-us/articles/360045138471-Discord-Voice-and-Video-Troubleshooting-Guide

**Belangrijk:** zet **CABLE Output niet als standaardmicrofoon van heel Windows**. Laat Windows op je Razer staan. Discord moet zelf CABLE Output kiezen. Als DrostSoundboard niet meer draait en Discord nog steeds CABLE Output gebruikt, krijgen anderen stilte. Je moet dan DrostSoundboard opnieuw verbinden of in Discord de Razer-microfoon terugkiezen.

## Stap 2. Maak een back-up

Sluit eerst DrostSoundboard. Open PowerShell.

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.py,.\DrostSoundboard\*.bat,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_webdashboard.zip -Force
```

## Stap 3. Installeer de update

Download `DrostSoundboard_Fase3_Web_Update.zip` in je map Downloads.

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase3_Web_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard
```

De `.venv` en de logboeken blijven staan. De bestaande SQLite-bibliotheek wordt niet overschreven.

## Stap 4. Herstel de ontbrekende MP3-afhankelijkheid

Je kreeg eerder `ModuleNotFoundError: No module named 'soundfile'`. Daarom moet je deze stap zeker uitvoeren.

```powershell
.\Installeer_ontwikkelomgeving.bat
```

Controleer daarna:

```powershell
.\.venv\Scripts\python.exe -c "import sounddevice, numpy, soundfile, soxr; print('Audiobibliotheken zijn klaar')"
```

Als je een fout krijgt, open dan de logmap met `Open_Logboeken.bat` en controleer `installatie.txt`. Probeer dan niet blind verder te starten.

## Stap 5. Voer de automatische tests uit

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Verwachte einduitvoer:

```text
Ran 144 tests

OK
```

De tests gebruiken nagebootste geluidsapparaten en een lokale HTTP-server. Ze vervangen de echte Razer- en Discord-test op jouw pc niet.

## Stap 6. Start de webpagina

```powershell
.\Start_DrostSoundboard.bat
```

Je browser opent automatisch het lokale dashboard. Open anders het adres dat in het PowerShell-venster staat, normaal `http://127.0.0.1:8765/`.

**Laat het PowerShell-venster open.** Je browser bedient de app, maar Python moet blijven draaien om de microfoonmix aan te bieden. Als je het terminalvenster sluit, stopt de audiomixer. Daarmee wordt CABLE Output stil.

## Stap 7. Controleer het geluid

1. Kies bovenin `Microfoon (Razer USB Sound Card)`.
2. Klik op **Verbinden**. Controleer of de microfoonmeter beweegt als je praat.
3. Controleer in `mmsys.cpl` onder **Opnemen** of ook **CABLE Output** reageert.
4. Zet de Soundboard-schakelaar aan.
5. Klik rechts op **Geluiden toevoegen** en kies een of meer MP3- of WAV-bestanden. Je kunt bijvoorbeeld `discord-call-sound.mp3` of `het_sneeuwt.mp3` uit Downloads kiezen.
6. Klik op een leeg favorietvak, kies een geluid en klik op de kaart om af te spelen.
7. Klik op het bewerkknopje bij een geluid om naam, begintijd, volume of fragmentduur in te stellen. De fragmentduur mag maximaal 120 seconden zijn. Je kunt ook een PNG, JPG, WEBP of GIF koppelen.
8. Klik tijdens een fragment op **Stop geluid**. Je microfoon moet blijven doorlopen.
9. Zet Soundboard uit. Je microfoon moet nog steeds doorgaan.
10. Klik pas op **Verbreken** wanneer je niet meer via CABLE Output wilt praten.

## Stap 8. Controleer de auditlogs

```powershell
.\Open_Logboeken.bat
```

In `audit.jsonl` staan de ingevoerde geluiden, favorietwijzigingen, verzoeken om af te spelen en de echte start- en stopmomenten van de audiomixer. Bij iedere afspeelbeurt worden onder andere de naam, startpositie, gevraagde duur, het volume en de daadwerkelijk aangeleverde audioseconden vastgelegd.

`software.jsonl` bevat bij onverwachte fouten de volledige traceback, de Python-functie, regelnummers, sessiegegevens en waar mogelijk de relevante parameters. `crashes.txt` is een extra vangnet voor enkele fatale Python-crashes. Bij een stroomuitval of zeer ernstige Windows-drivercrash kan niemand garanderen dat de laatste logregel nog op schijf wordt geschreven.

## Wat als het niet werkt?

**De webpagina opent niet:** kijk of in PowerShell een adres staat. Probeer dat handmatig. Als het programma gestopt is, controleer `software.jsonl`. Gebruik niet een URL die naar een ander apparaat verwijst. De server luistert alleen op `127.0.0.1`.

**Python mist soundfile of soxr:** voer `Installeer_ontwikkelomgeving.bat` opnieuw uit. Controleer de laatste regels van `installatie.txt`.

**MP3 wordt niet toegevoegd:** importeer een echte MP3 en controleer of het bestand minder dan 250 MiB is. Een bestand met een .mp3-extensie kan nog steeds corrupt zijn.

**Discord hoort je stem wel en de muziek niet:** zet Krisp tijdelijk uit, kies Spraakactiviteit, controleer microfoonvolume en test met de doorlopende controletoon. Test vervolgens met een echt persoon.

**Je spreekt niet meer nadat je DrostSoundboard afsluit:** Discord staat dan nog op CABLE Output. Open DrostSoundboard en verbind opnieuw, of zet de invoer van Discord tijdelijk terug op de fysieke Razer-microfoon.

**De webpagina draait maar je hoort niets via je eigen headset:** dat is normaal. Geluiden worden rechtstreeks naar de virtuele kabel gestuurd. De headset krijgt op dit moment geen apart monitorpad.

**Ik wil terug naar het oude Windows-venster:** gebruik `Start_Oud_Windowsvenster.bat`. Start niet beide interfaces tegelijk op dezelfde audiokabel.

## Wat zit nog niet in deze fase?

Dit is de eerste echte lokale webversie van de applicatie, geen definitief `.exe`-installatieprogramma. De eindgebruikersinstaller zonder aparte Python-installatie blijft een volgende mijlpaal. Ook volledige muziekstreaming zonder eerst maximaal 120 seconden in geheugen voor te bereiden, MP4-voorbeelden en automatische omschakeling van de microfoon in externe belapps zijn nog niet gebouwd.
