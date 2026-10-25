# INSTALLEREN: DrostSoundboard stap voor stap

**Huidige status:** fase 0 en fase 1A (de echte kabeltest) zijn op de ontwikkelcomputer geslaagd. Fase 1B voegt een tijdelijk venster toe om eigen WAV-geluiden te kiezen, af te spelen en te stoppen. De echte hardwaretest van dat venster moet nog gebeuren. **Volg daarvoor eerst `FASE1B_TESTEN.md`.** De microfoonmix, het HTML-dashboard en de definitieve Windows-installer worden later gebouwd. Dit document blijft de algemene ontwikkel- en toekomstige installatiehandleiding.

## Deel A. Eerste keer op je eigen Windows 11-pc

### Stap 1. Controleer de audioapparaten zonder iets te veranderen

1. Druk op `Windows + R`.
2. Typ `mmsys.cpl` en druk op Enter.
3. Open **Afspelen**. Controleer dat **Luidsprekers (Razer USB Sound Card)** het normale standaardapparaat is. Als dit niet zo is, selecteer de Razer en klik op **Als standaard instellen**.
4. Zoek ook naar **CABLE Input (VB-Audio Virtual Cable)**. Je hoeft deze **niet** als standaarduitvoer in te stellen.
5. Open **Opnemen**. Zoek de echte Razer-microfoon en **CABLE Output (VB-Audio Virtual Cable)**. Schrijf de namen op zoals Windows ze toont.
6. Sluit dit venster met OK. Verander op dit moment de standaard Windows-microfoon niet.

Op jouw screenshots is gecontroleerd dat Razer de standaardluidspreker en standaardmicrofoon is en dat CABLE Input en CABLE Output beide gereed zijn. Laat deze instellingen dus staan.

### Stap 2. Als VB-CABLE ontbreekt

Sla deze stap over als **CABLE Input** en **CABLE Output** allebei aanwezig zijn. Op jouw screenshots van 23 oktober 2026 is dat bevestigd: beide apparaten zijn gereed.

1. Ga naar de officiële site: https://vb-audio.com/Cable/
2. Download de Windows-driver van VB-CABLE.
3. Pak het zipbestand volledig uit.
4. Start het geschikte setup-programma vanuit de uitgepakte map met **Als administrator uitvoeren** en kies installeren.
5. Start Windows opnieuw. Volgens de maker is die herstart onderdeel van de installatie.
6. Controleer opnieuw met `mmsys.cpl` dat de twee audioapparaten aanwezig zijn.
7. Controleer na driverinstallatie of je Razer nog steeds de standaard Windows-luidspreker is. Een nieuw stuurprogramma kan de standaardkeuze veranderen.

We bundelen de VB-CABLE-driver niet zonder eerst de distributievoorwaarden te controleren. De gewone soundboard-app zelf heeft geen beheerdersrechten nodig voor normaal gebruik.

### Stap 3. Microfoontoegang in Windows

1. Open **Instellingen**.
2. Kies **Privacy en beveiliging** en daarna **Microfoon**.
3. Zet **Microfoontoegang** aan.
4. Zet **Apps toegang geven tot uw microfoon** aan, als die optie wordt getoond.
5. Zet **Bureaublad-apps toegang geven tot uw microfoon** aan.

Als je microfoon niet zichtbaar is, controleer dan de kabel, USB-aansluiting en Windows-audiodriver voordat je iets in Python probeert.

### Stap 4. Controleer Python voor ontwikkeling

Python is op jouw pc al geïnstalleerd. Je hebt `Python 3.13.15` bevestigd. Daarom hoef je Python niet opnieuw te installeren. Je kunt controleren met:

```powershell
py -3.13 --version
```

Verwacht: een Python-versie die begint met `Python 3.13`. Als `py` niet bestaat, controleer dan eerst of Python goed is geïnstalleerd. Probeer anders `python --version` en kijk of dat daadwerkelijk versie 3.13 is. Download Python desnoods via https://www.python.org/downloads/windows/.

We kiezen hier bewust één ontwikkelversie om verschillen tussen computers te beperken. Eindgebruikers hoeven later **geen Python** te installeren.

### Stap 5. Download en pak de projectmap uit

Pak `DrostSoundboard_Starter.zip` uit **in** de map `C:\Users\jelle\Desktop\pythonProjects`. Binnen de ZIP staat al een hoofdmap `DrostSoundboard`, zodat de volledige projectmap wordt:

```text
C:\Users\jelle\Desktop\pythonProjects\DrostSoundboard
```

Je ziet in Verkenner dan `DrostSoundboard` **naast** `mc`, `pctest` en `TranscriptieThuis`. Controleer dat je niet per ongeluk een dubbele map `DrostSoundboard\DrostSoundboard` hebt gemaakt. In de juiste hoofdmap staan `main.py`, `requirements.txt` en `Start_DrostSoundboard.bat`.

**Het makkelijkst:** dubbelklik eenmalig op `Installeer_ontwikkelomgeving.bat`. Dit script maakt `.venv` aan en installeert de afhankelijkheden. Daarna hoef je alleen `Start_DrostSoundboard.bat` te openen.

**Liever via PowerShell?** Gebruik onderstaande opdrachten. Je hoeft de installatiebatch dan niet uit te voeren.

Open PowerShell en voer uit:

```powershell
cd C:\Users\jelle\Desktop\pythonProjects\DrostSoundboard
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

De map `.venv` is je eigen Python-omgeving voor dit project. Door het Python-bestand direct uit `.venv` te gebruiken, hoef je niets te activeren en hoef je het PowerShell-uitvoeringsbeleid niet aan te passen.

### Stap 6. Start de fase 0-apparaatcontrole

Dubbelklik in de projectmap op:

```text
Start_DrostSoundboard.bat
```

Of voer in PowerShell uit:

```powershell
.\.venv\Scripts\python.exe main.py
```

De starter toont nu de gevonden Windows-audioapparaten. Hij heeft geen parameters of argumenten nodig. Je moet onder de invoer de microfoon en CABLE Output terugvinden; onder de uitvoer CABLE Input en de Razer-speakers. Als apparaten ontbreken, blijft de diagnose zichtbaar in plaats van stilzwijgend een willekeurig apparaat te kiezen.

**Let op:** in fase 0 wordt nog **geen** audio van je microfoon naar CABLE Input gestuurd. Zet Discord nu dus nog niet permanent op CABLE Output. Dat doen we nadat fase 1 en 2 zijn getest.

### Stap 7. Controleer de logs

Druk op `Windows + R` en voer dit in:

```text
%LOCALAPPDATA%\DrostSoundboard\logboeken
```

Je kunt ook dubbelklikken op `Open_Logboeken.bat` in de projectmap.

Daar staan minstens:

```text
software.jsonl
audit.jsonl
crashes.txt
```

In `software.jsonl` staan de sessie, de apparaatinventaris en foutdetails. In `audit.jsonl` staan voorlopig alleen de start en afronding van de apparaatcontrole. Vanaf fase 1 komen daar geluidsafspeelbeurten bij. `crashes.txt` mag bij een goede start leeg zijn.

### Stap 8. Voer de tests uit

Terug in PowerShell, vanuit de projectmap:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Verwacht: de tests eindigen op `OK`. Ze testen de logstructuur en apparaatverwerking zonder fysieke audio op te nemen.

### Stap 9. Houd de instellingen voorlopig veilig

Laat **Razer USB Sound Card** als standaard Windows-afspeelapparaat staan. Laat de standaard Windows-microfoon voorlopig op je normale Razer staan. Gebruik nog geen CABLE Output in Discord zolang we de mixer niet echt hebben gebouwd.

## Deel B. Gebruik van de uiteindelijke soundboard-app

Dit deel is een **ontwerp voor de toekomstige installer**, nog geen claim dat het al beschikbaar is.

1. Download de officiële, later te bouwen Windows-installer van het project.
2. Start de installer en laat hem de app onder de normale Windows-programmamap installeren.
3. Als WebView2 ontbreekt, laat de installer je de officiële Microsoft Runtime installeren of, na toestemming, de officiële installer starten. Hiervoor kan internet nodig zijn.
4. Als VB-CABLE ontbreekt, krijg je een duidelijke instructie en de officiële downloadlink; voor de driver kunnen beheerdersrechten en een reboot nodig zijn.
5. Open de app vanuit het startmenu of de snelkoppeling. Python of PowerShell is dan niet nodig.
6. Kies bij de eerste start jouw microfoon en controleer de virtuele kabel.
7. Open Discord en selecteer één keer CABLE Output als invoerapparaat. Laat Razer de geluidsuitvoer zijn.
8. Klik op **Verbinden**. Kies **Soundboard aan** om geluidjes door te sturen. Kies **Soundboard uit** om zonder geluidseffecten te blijven praten.
9. Als je **Verbinding verbreken** of **Afsluiten** kiest, kan CABLE Output stil worden. Selecteer in de belapp de Razer-microfoon als je zonder app verder praat.
10. Bij problemen kies je **Audio herstellen** of **Open logmap**.

Voor de eerste officiële release richten we ons op **Windows 11 x64**. Het doel is installatie zonder Python en zonder ontwikkeltools op een schone pc. We kunnen niet eerlijk beloven dat elke Windows-pc werkt, omdat drivers, USB- of Bluetooth-hardware, rechten en Windows-versies verschillen.

## Deel C. Discord, pas na een werkende audiomixer

1. Open Discord en ga naar **Gebruikersinstellingen**.
2. Open **Spraak en video**.
3. Kies bij **Invoerapparaat** de opnamekant van VB-CABLE, meestal `CABLE Output`.
4. Kies bij **Uitvoerapparaat** de Razer-headset.
5. Start de audiomixer in DrostSoundboard met **Verbinden**.
6. Spreek in de microfoon en gebruik een testgeluid.
7. Als effecten niet doorkomen, vergelijk de geluidskwaliteit met **Krisp / ruisonderdrukking** uitgeschakeld. Dat filter is bedoeld om niet-spraakgeluiden tegen te houden.
8. Test de uiteindelijke werking met een tweede persoon. Discord kan de binnenkomende audio comprimeren of verwerken.

Voor WhatsApp Desktop kies je waar de gebruikte versie dat toestaat ook `CABLE Output` als microfoon. Als deze versie geen microfoonkeuze aanbiedt, moet je mogelijk de Windows-standaardopnamebron kiezen. Doe dat bewust, want andere apps kunnen die standaardbron ook gebruiken.

## Deel D. Bekende problemen en eerste oplossing

| Situatie | Controleer eerst |
| --- | --- |
| `py` wordt niet gevonden | Python-installatie, nieuw PowerShell-venster en versiecontrole. |
| `.venv` bestaat niet | Voer `py -3.13 -m venv .venv` uit in de juiste projectmap. |
| `sounddevice` of `numpy` ontbreekt | Voer `...python.exe -m pip install -r requirements.txt` opnieuw uit. |
| CABLE Input ontbreekt | VB-CABLE installeren en Windows herstarten. |
| CABLE Output ontbreekt | Klassieke Windows-geluidsinstellingen, tabblad Opnemen. |
| Razer-microfoon ontbreekt | Razer aansluiten, controleren bij Opnemen en Windows-microfoonrechten. |
| Discord hoort niets | Eerst testen of de audiomixer actief doorstuurt, daarna Input Device controleren. |
| Alleen geluiden, geen stem | Fysieke microfoonselectie, mute en verbindingsstand nakijken. |
| Alleen stem, geen geluiden | Soundboard ingeschakeld, effectvolume en Discord-filters controleren. |
| AirPods geven slechter geluid | Bluetooth-handsfreeprofiel kan kwaliteit beperken. |
| App lijkt kapot | Bekijk `software.jsonl`, `audit.jsonl` en zo nodig `crashes.txt`. |

## Documentatie

- Projectplan: `DrostSoundboard_Projectplan.md`
- Richtlijnen voor code: `CONTRIBUTING.md`
- Overzicht: `README.md`
- VB-CABLE: https://vb-audio.com/Cable/
- WebView2: https://developer.microsoft.com/microsoft-edge/webview2/
- Python: https://www.python.org/downloads/windows/

## Deel E. Fase 1: automatische kabeltest

De benodigde Python-omgeving is op de ontwikkelcomputer al geïnstalleerd. Volg `FASE1_TESTEN.md` voor het uitpakken van de update en start daarna `Test_Virtuele_Kabel.bat`. Deze test speelt alleen een zachte toon in `CABLE Input` en meet het resultaat via `CABLE Output`. De Razer-microfoon wordt niet geopend. Je hoeft nog geen Discord-instellingen te veranderen.

## Deel E. De WAV-test in fase 1B

Bij een bestaande projectinstallatie installeer je de fase 1B-update volgens `FASE1B_TESTEN.md`. Draai daarna eenmalig `Installeer_ontwikkelomgeving.bat` om NumPy te installeren. Start `Speel_Eigen_Geluid.bat` zonder parameters. Dit opent een tijdelijk venster waarmee je één WAV per keer via VB-CABLE test. De test opent je fysieke microfoon niet. Voor echte Discord-gesprekken moet de continue microfoonmix eerst nog worden gebouwd.

## Actuele aanvulling: starten vanaf het lokale webdashboard

Na fase 3 opent `Start_DrostSoundboard.bat` automatisch `http://127.0.0.1:8765/` in de standaardbrowser. Er zijn geen parameters nodig. Python en de applicatie moeten blijven draaien zolang Discord CABLE Output gebruikt. Als die poort bezet is, meldt PowerShell het automatisch gekozen adres.

Een ontwikkelaar voert na een update altijd eerst `Installeer_ontwikkelomgeving.bat` uit. Dat script controleert nu ook of `sounddevice`, `numpy`, `soundfile` en `soxr` werkelijk geladen kunnen worden. Daarmee voorkomen we de eerder aangetroffen fout `ModuleNotFoundError: No module named 'soundfile'` na alleen uitpakken.

Dit is nog de ontwikkelinstallatie. De zelfstandige Windows-installer zonder Python is een afzonderlijk onderdeel van de planning. Zie `FASE3_WEBDASHBOARD_TESTEN.md` voor de actuele stappen en Discord-test.
