> **Update 23 oktober 2026, fase 2.2:** De fysieke Razer-microfoon leverde bij een losse opname meetbaar geluid (`hoogste_rms 0.1370048`). De live-mixer liep bij het starten herhaald tegen `WdmSyncIoctl ... GLE 0x00000006` aan maar slaagde later alsnog na meerdere handmatige pogingen. Daarna werden WAV-geluiden correct gestart en gestopt, zonder gemelde bufferproblemen. Deze update initialiseert Windows COM in de audio-werkdraad en voert bij uitsluitend dit specifieke driverprobleem maximaal vijf automatische herstelpogingen uit, met tracebacks en auditlogging. **De nieuwe herstelcode is alleen met gesimuleerde audioapparaten getest en moet nog op de echte Windows-computer worden bevestigd.** Zie `FASE2_AUDIOSTART_HERSTELLEN.md`.

> **Status 23 oktober 2026, fase 2:** 45 automatische tests van fase 1B geslaagd op de gebruikerscomputer en één daadwerkelijk aangeboden WAV-bestand van 8 seconden (geen bufferproblemen). Nieuwe live mixer met Razer-microfoon als voorkeur, WASAPI-duplexstream, aan/uit voor geluidseffecten, verbinden/verbreken en auditlogging is geprogrammeerd. 64 lokale automatische tests geslaagd met nepdrivers. **Nog niet op de fysieke Windows-microfoon getest.** Zie `FASE2_TESTEN.md` voor de volgende tests.

# DrostSoundboard, projectplan 2.2 voor Windows

**Datum:** 23 oktober 2026  
**Status:** Fase 0, fase 1A en het volledig afspelen van een WAV-bestand uit fase 1B zijn op de echte Windows-pc geslaagd. Handmatig stoppen van dat WAV-bestand is op die pc nog niet bevestigd. Fase 2 bevat een eerste live microfoonmix en de drie gewenste standen. Deze nieuwe onderdelen zijn met gesimuleerde drivers getest, maar nog niet op de echte Razer-microfoon. Het HTML-dashboard, de mediabibliotheek en de definitieve Windows-installer worden later gebouwd.  
**Eerste ondersteunde doelomgeving:** Windows 11, 64 bit, met werkende Windows-audiodrivers. Andere Windows-versies en ARM64 pas na afzonderlijke tests.

## 1. Wat we bouwen

Een snelle lokale desktopapplicatie waarin je zelf geluiden toevoegt, een naam en categorie geeft, er een afbeelding, GIF of MP4 bij zet en op een kaart klikt om het fragment af te spelen. Terwijl je praat, hoort je gesprekspartner je stem en het geluid via de virtuele microfoon van VB-CABLE. De gebruiker kan zelf kiezen tussen bijvoorbeeld de Razer-microfoon en een verbonden AirPods-microfoon.

De interface wordt gebouwd met HTML, CSS en JavaScript. Python beheert de geluidsbibliotheek, audiomixer, instellingen, apparaten en logging. `pywebview` toont het dashboard als een normale Windows-app. `sounddevice` en NumPy verzorgen de audiostromen. SQLite bewaart de bibliotheek. De app werkt lokaal zonder account of internetverbinding, afgezien van eventuele eenmalige softwaredownloads.

Het is **geen** project om zelf een virtuele Windows-audiodriver te schrijven. Hiervoor gebruiken we VB-CABLE. Het is ook geen oplossing voor een WhatsApp-gesprek dat rechtstreeks op een telefoon buiten de Windows-pc plaatsvindt.

## 2. Bedieningsgemak is een harde eis

De uiteindelijke app start met een dubbelklik op `DrostSoundboard.exe`, zonder argumenten, terminal of aparte webserver die de gebruiker zelf moet opstarten.

### Drie verbindingsstanden

| Stand in het dashboard | Intern gedrag | Wat hoort Discord via CABLE Output? |
| --- | --- | --- |
| **Soundboard aan** | Microfoonstream en geluidseffecten worden gemengd en naar CABLE Input gestuurd. | Stem en geluiden. |
| **Soundboard uit** | De audiostream blijft open; alleen de microfoon wordt doorgestuurd. | Alleen stem, zonder de app opnieuw in te stellen. |
| **Verbinding verbreken** | Audioapparaten/streams worden netjes gesloten. | Stilte, zolang Discord CABLE Output blijft gebruiken. |

Er komt één goed zichtbare schakelaar **Soundboard aan/uit**. Daarnaast, in een duidelijk aparte bediening, een knop **Verbinden / Verbinding verbreken** en een knop **Audio herstellen** voor problemen. Een groot statusvak laat zien welke microfoon, welke virtuele kabel en welke monitoruitvoer actief zijn.

**Dit is een belangrijke technische beperking:** geen app kan garanderen dat Discord of WhatsApp automatisch een andere microfoon kiest zodra we VB-CABLE niet meer vullen. Wie de applicatie volledig afsluit, kiest in de belapp weer zijn fysieke microfoon. Als we de app open laten en alleen het soundboard uitschakelen, is omschakelen in de belapp niet nodig.

**Bij fouten:** geen schijnbaar groene verbinding. Een onderbroken fysieke microfoon geeft zichtbaar `Microfoon ontbreekt`; bij mislukte audio-uitvoer staat `Geen verbinding met VB-CABLE`. Een herstartknop probeert de audio veilig opnieuw op te bouwen en noteert wat er gebeurde.

### Wat je als gebruiker wel en niet hoeft te doen

**Eenmalig per Windows-pc:** VB-CABLE controleren of installeren, een eventuele WebView2 Runtime verzorgen, een fysieke microfoon kiezen en in Discord / WhatsApp de juiste invoer selecteren. Na installatie en eerste configuratie bewaart de app de apparaten en instellingen.

**Bij normaal gebruik:** app openen, op **Verbinden** klikken als deze nog niet verbonden is, geluiden gebruiken en met **Soundboard uit** alleen je stem laten doorgaan. Bij voorkeur start de app later automatisch in de veilige stand `Soundboard uit, microfoon doorgeven`, maar pas na toestemming van de gebruiker in de instellingen.

**Bij volledig stoppen:** de app waarschuwt dat CABLE Output kan wegvallen en biedt een korte instructie om in de belapp terug te schakelen naar de Razer-microfoon. De app verandert niet stiekem het standaard Windows-opnameapparaat.

### Andere bruikbaarheidseisen

1. Een geluidskaart werkt met één klik. Nogmaals klikken stopt of herstart het fragment volgens een per-geluid ingestelde keuze.
2. Duidelijke knoppen voor **Alles stoppen**, **Microfoon dempen**, **Soundboard uit**, **Lokaal horen aan/uit** en **Apparaten kiezen**.
3. Instellingen voor Razer en AirPods als herkenbare profielen. Apparaten op naam en eigenschappen herkennen, niet op een vast nummer dat na herstart kan veranderen.
4. Een simpele eerste-start-wizard met controles voor microfoon, VB-CABLE, luidspreker en privacyrechten.
5. De app start ook zonder VB-CABLE in **Bibliotheek bekijken** en legt uit waarom doorsturen niet mogelijk is.
6. Geen geluid afspelen bij het importeren van een bestand, tenzij de gebruiker daar expliciet om vraagt.
7. De gewone Windows-geluidsuitvoer blijft op de Razer-headset. Geen systeemgeluid terug de microfoon in sturen.

## 3. Precieze audiorouting

1. Python opent de geselecteerde fysieke opnamebron, bijvoorbeeld de Razer-microfoon.
2. Het geluid van die microfoon wordt continu ontvangen.
3. Geluidseffecten worden vooraf gedecodeerd en in een aparte wachtrij gezet.
4. De audiomixer verwerkt beide bronnen op een intern formaat van 48.000 Hz en float32.
5. In de stand **Soundboard uit** worden effecten niet toegevoegd. In de stand **Soundboard aan** wel.
6. De gemixte stream wordt afgespeeld naar **CABLE Input** van VB-CABLE.
7. De belapp neemt op van **CABLE Output**, de virtuele opnamekant van dezelfde kabel.
8. De Razer blijft de gewone luidspreker in Windows. Lokale weergave van effecten loopt via een afzonderlijk monitorpad, indien ingeschakeld.

Bij verschillende klokken van de fysieke microfoon en CABLE Input zijn ringbuffers en gecontroleerde driftcompensatie nodig. Gebruik gedeelde WASAPI-toegang als standaard. De callback van de audiostream doet **geen** bestandstoegang, databasequeries, videodecodering, ingewikkelde logging of UI-calls. UI en auditgebeurtenissen komen via een veilige wachtrij in een andere thread terecht.

De app start bewust zonder audiobewerking die ongetest stemmen kan vervormen. Voor de uiteindelijke mixer zijn microfoonvolume, effectvolume, een limiter, fade-in / fade-out en fouttellers nodig. Herhaald over-/onderlopen van buffers wordt geteld en periodiek gelogd, niet voor ieder sample apart.

**AirPods:** gebruik als opnameapparaat is mogelijk als Windows ze aanbiedt. Bluetooth-handsfree-audio kan de geluidskwaliteit verlagen of het apparaat tijdelijk laten verdwijnen. De app belooft niet dat Bluetooth zonder onderbreking wisselt.

## 4. Taal, namen en modulaire architectuur

**Alle zelfgeschreven identifiers, foutmeldingen, commentaar en documentatie zijn in duidelijk Nederlands.** Alleen Python-sleutelwoorden, bibliotheeknamen, verplichte externe API-velden en standaardbestandsnamen blijven technisch Engels. Namen zijn beschrijvend, liever lang dan cryptisch.

Voorbeelden:

```python
def verbind_geselecteerde_microfoon_met_virtuele_kabel(gekozen_microfoon, gekozen_kabel):
    """Open beide geluidsapparaten en bereid het doorsturen van de stem voor."""


def maak_auditregel_voor_afgespeeld_geluid(geluidsnummer, afspeelbeurt_nummer, tijdstip):
    """Leg vast welk geluidsfragment wanneer is gestart."""
```

Bestandsindeling aan het einde van het project:

```text
DrostSoundboard/
    main.py                         # Altijd zonder argumenten starten
    Installeer_ontwikkelomgeving.bat  # Eenmalig voor ontwikkelaars
    Start_DrostSoundboard.bat          # Zonder argumenten starten in ontwikkeling
    Open_Logboeken.bat                 # Logmap openen
    requirements.txt
    README.md
    INSTALLEREN.md
    CONTRIBUTING.md
    DrostSoundboard_Projectplan.md
    Speel_Eigen_Geluid.bat            # Tijdelijk venster voor fase 1B
    speel_eigen_geluid.py              # Opstarten zonder argumenten
    FASE1B_TESTEN.md
    app/
        vensters/
            venster_voor_geluidstest.py   # Tijdelijke testinterface
        audio/
            geluidsbestanden.py     # In fase 1B WAV lezen en voorbereiden
            geluid_afspelen.py      # In fase 1B één geluid naar VB-CABLE
            geluidsmotor.py         # Starten, stoppen en herstellen
            apparatenbeheer.py      # Microfoons en audio-uitvoer zoeken
            geluidsmixer.py         # Stem en effecten mengen
            afspeelwachtrij.py      # Actieve fragmenten en timing
            geluidsbuffer.py        # Ringbuffers en klokverschillen
        bibliotheek/
            geluidenopslag.py       # SQLite en wijzigingen
            mediabeheer.py          # Audio importeren, afbeeldingen, video
        communicatie/
            venster_koppeling.py    # JavaScript naar gecontroleerde Python-acties
            invoercontrole.py       # Verplichte, lege en extra parameters
        diagnostiek/
            logboek.py              # Gestructureerde technische logging
            auditlog.py             # Gebeurtenissen met afspeelbeurten
            foutafhandeling.py      # Foutcodes en zichtbare meldingen
            diagnose_exporteren.py  # Geanonimiseerde supportbundel
        instellingen/
            instellingenbeheer.py
        interface/
            index.html
            css/dashboard.css
            js/dashboard.js
            js/bibliotheek.js
            js/apparaten.js
    voorbeelden/
        voorbeeld_ping.wav
        voorbeeld_lang_8seconden.wav
    tests/
        test_apparatenbeheer.py
        test_geluidsmixer.py
        test_auditlog.py
        test_invoercontrole.py
        test_verbindingstoestanden.py
    installatie/
        maak_installer.ps1
        soundboard_installer.iss
```

De eerste fase bevat alleen een kleine subset van deze modules. We maken de rest pas wanneer de vorige stap betrouwbaar werkt. Dit voorkomt lege sjabloonbestanden en een schijnbaar afgeronde app.

## 5. Logging is een hoofdonderdeel, geen bijzaak

Er zijn **drie soorten registraties**:

| Type | Bevat | Standaard bewaartermijn voor eindversie |
| --- | --- | --- |
| **Auditlog** (`audit.jsonl` en geroteerde bestanden) | Wie of wat startte en stopte een geluid, welk fragment, begin, einde, echte duur, volume, resultaat. Ook verbinden, verbreken en instellingenwijzigingen. | 90 dagen, instelbaar |
| **Softwarelog** (`software.jsonl`) | Opstarten, sluiting, apparaten, versie, waarschuwingen, problemen met afhankelijkheden en volledige exceptiongegevens. | 30 dagen, instelbaar |
| **Crashlog** (`crashes.txt`) | Tracebacks van onverwachte fouten en, waar mogelijk, extra informatie over fatale Python-fouten. | 30 dagen, instelbaar |

Alle logbestanden staan buiten de programmamap, bijvoorbeeld `%LOCALAPPDATA%\DrostSoundboard\logboeken`. De uiteindelijke app biedt **Open logmap**, **Kopieer foutdetails** en **Maak diagnosepakket**. Er is geen automatische verzending van logs naar een server.

### Verplichte velden voor de softwarelog

`tijd_utc`, `niveau`, `sessie_id`, `gebeurtenis`, `component`, `functie`, `bestandsnaam`, `regelnummer`, `appversie`, `bericht`, `foutcode`, `fouttype`, `foutmelding`, `traceback` en veilige technische context voor zover van toepassing.

Bij een fout door een functieaanroep registreren we ook:

1. Welke parameter of veldnaam ontbreekt.
2. Welke type of waarde werd verwacht.
3. Welk type werkelijk werd ontvangen, bijvoorbeeld `NoneType`, `str` of `int`.
4. Of onbekende of extra velden werden doorgegeven.
5. Welke afhankelijkheid of welk apparaat ontbreekt of niet geopend kon worden.
6. De originele exceptie, de oorzaakketen (`raise ... from ...`) en de volledige traceback.
7. Welke actie werd uitgevoerd, bijvoorbeeld `verbinden_met_kabel`, en het unieke actie- of sessienummer.

Niet elke denkbare fout onthult automatisch **waarom** iets in werkelijkheid misging. Log daarom voldoende veilige context en geef een concrete foutcode. Bij een driverfout kan de onderliggende Windows- of PortAudio-code de oorzaak verduidelijken, maar niet altijd bewijzen.

### Verplichte velden voor iedere afspeelbeurt

`afspeelbeurt_id`, `geluid_id`, `geluidsnaam_op_moment_van_afspelen`, `gestart_utc`, `gestopt_utc`, `geplande_duur_ms`, `werkelijke_duur_ms`, `volume`, `afspeelresultaat`, `stopreden`, `route` en `sessie_id`.

Auditgebeurtenissen in de implementatie:

`geluid_aangevraagd`, `geluid_gestart`, `geluid_beeindigd`, `geluid_geweigerd`, `geluid_mislukt`, `soundboard_ingeschakeld`, `soundboard_uitgeschakeld`, `verbinding_gestart`, `verbinding_verbroken`, `apparaat_gewijzigd`, `instelling_gewijzigd`.

We meten de echte afspeelduur vanuit de audiomotor en niet alleen de lengte van het audiobestand. Een geluid dat je na 1 seconde stopt, krijgt dus ongeveer 1 seconde als werkelijke duur, plus de nauwkeurigheid van de audiobuffers. Elke gelijktijdige afspeelbeurt heeft een eigen identificatie.

**Privacy en prestaties:** log standaard geen opname van de microfoon, inhoud van gesprekken, wachtwoorden of ruwe audiobuffers. Absolute privébestandenpaden worden in exportpakketten verwijderd of ingekort. Schrijf vanuit de realtime audiocallback niet direct naar schijf. Gebruik een begrensde logwachtrij en schrijf duidelijk weg als logberichten door een volle wachtrij verloren dreigen te gaan. Logs worden geroteerd, zodat de schijf niet eindeloos volloopt.

**Grenzen:** gewone lokale auditbestanden zijn niet manipulatiebestendig. Voor juridisch sluitende of niet-wijzigbare auditsporen zou een extra ondertekend of extern opslagmechanisme nodig zijn. Als de pc hard uitgaat of de schijf vol is, kan geen applicatie alle laatste logregels garanderen.

## 6. Validatie en foutenafhandeling

Bij iedere externe grens controleren we gegevens expliciet: JavaScript-opdrachten, geïmporteerde bestanden, instellingen en apparaten. We accepteren geen onbekende actie of stilzwijgend genegeerde extra parameters. Verplichte waarden mogen niet ontbreken, `None` zijn, leeg zijn of van een verkeerd type zijn. We controleren bestandspaden, ondersteunde extensies en maximale bestandsgrootte voordat import start.

Geldige foutmeldingen benoemen het probleem en de volgende stap: `AUDIO-003: De gekozen microfoon is niet meer beschikbaar. Kies een andere microfoon of druk op Audio herstellen.` Een technisch log bevat vervolgens de uitzondering met originele traceback en context. De interface toont niet zomaar een intimiderende traceback aan de gebruiker.

Gebruik specifieke excepties en `logger.exception` binnen `except`-blokken. Bij onverwachte fouten bewaren we de traceback en sluiten we alleen de getroffen taak af als veilig herstel mogelijk is. Geen kale `except: pass`, geen `print()` als enige foutafhandeling en geen volledig leeg resultaat teruggeven alsof iets gelukt is.

Test expliciet: ontbrekende module, fout apparaatnummer, onbekende audiobron, extra JSON-parameter, ontbrekende titel, `None`, lege string, niet-bestaand bestand, beschadigde MP3, volle opslag, weggehaalde USB-microfoon, wegvallende AirPods, niet-beschikbare VB-CABLE en een geforceerde fout in een achtergrondthread.

## 7. Bibliotheek en media

SQLite bewaart per geluid: `geluid_id`, `naam`, `categorie`, `zoekwoorden`, `audiobestand`, `afbeelding_of_video`, `totale_duur_ms`, `eigen_volume`, `favoriet`, `sneltoets`, `toegevoegd_utc` en `bijgewerkt_utc`.

Geïmporteerde bestanden worden gekopieerd naar de bibliotheek binnen `%LOCALAPPDATA%\DrostSoundboard\bibliotheek`. Gebruikers hoeven het origineel dus niet te laten staan. Thumbnails maken we op de achtergrond. GIF of MP4 is alleen het beeld bij een kaart; de video speelt standaard zonder eigen geluid. Geluid uit een MP4 wordt indien gewenst bij import éénmalig omgezet naar een apart audiobestand. Gebruik FFmpeg alleen als deze extra functies daadwerkelijk nodig zijn; controleer bij verspreiding de bijbehorende licenties.

## 8. Exacte ontwikkelfases

### Fase 0. Windows en apparaten controleren. Afgerond op de ontwikkelcomputer.

**Ontwikkelmap:** `C:\Users\jelle\Desktop\pythonProjects\DrostSoundboard`. De eerder gedeelde screenshots bevestigen Razer als standaardmicrofoon en standaarduitvoer, beide VB-CABLE-kanten als gereed, en `Python 3.13.15` is geïnstalleerd. Nu blijven de projectinstallatie, de apparaatcontrole vanuit Python en de logs over.

1. Bekijk `INSTALLEREN.md` en controleer de Windows-instellingen.
2. Python 3.13 staat al op de ontwikkelcomputer. Pak de nieuwe ZIP uit naast de andere projecten. Dubbelklik op `Installeer_ontwikkelomgeving.bat` om `.venv` en `requirements.txt` klaar te zetten, of gebruik de opdrachten in `INSTALLEREN.md`.
3. Start `Start_DrostSoundboard.bat`, zonder argumenten. **Let op:** voorlopig toont deze starter alleen de apparaatcontrole en schrijft hij software- en auditlogs. Dit is nog niet het daadwerkelijke soundboard.
4. Controleer dat de uitvoer `CABLE Input`, de invoer `CABLE Output` en de Razer-microfoon bevat.
5. Controleer de logmap en voer de meegeleverde unit-tests uit.
6. Verander in Discord nog niets voordat fase 1 werkt; daarmee voorkom je een stille microfoon.

**Klaar als:** apparaten worden gevonden of met een duidelijke waarschuwing gemist, er is een uitvoerbaar startbestand, en softwarelog/auditlog zijn aangemaakt. Je hebt de precieze namen van de apparaten.

### Fase 1. Geluidsuitvoer via VB-CABLE. Fase 1A geslaagd, 1B klaar voor de Windows-test.

1. **Fase 1A is voorbereid:** `Test_Virtuele_Kabel.bat` zoekt de gewone CABLE Input en CABLE Output via Windows WASAPI op naam, niet op een vast nummer.
2. De audiotest maakt een zachte toon van 440 Hz van 1,8 seconde in het geheugen. Hiervoor hoeven nog geen audiobestanden te worden geïmporteerd. De Python-code opent de fysieke Razer-microfoon niet.
3. De test speelt de toon naar CABLE Input en meet CABLE Output tegelijk. We toetsen ook of de eigen frequentie van 440 Hz herkenbaar is, zodat achtergrondruis niet zomaar als geslaagd wordt gezien. Alleen meetwaarden en eventuele bufferproblemen worden bewaard, geen opgenomen audio-inhoud.
4. Het auditlog legt de start en afronding van de kabeltest vast, plus `geluid_gestart` en `geluid_gestopt` met een eigen afspeelbeurt-id, ingestelde volume en daadwerkelijke duur.
5. **Fase 1A afgerond op 23 oktober 2026:** de echte test met WASAPI 21 en 23 gaf 153.600 opgenomen frames, RMS 0,05875, toonherkenning 0,00311 en nul bufferproblemen. Dit bewijst dat VB-CABLE lokaal werkt; niet dat een belapp al audio ontvangt.
6. **Fase 1B ontwikkeld:** `Speel_Eigen_Geluid.bat` opent een klein tijdelijk testvenster met **Kies WAV**, **Afspelen**, **Stop** en **Sluiten**. Je kunt een PCM WAV van maximaal 45 seconden kiezen of een meegeleverd voorbeeld starten.
7. `app/audio/geluidsbestanden.py` doet validatie en maakt 48 kHz stereo float32-audio klaar. `app/audio/geluid_afspelen.py` stuurt de blokken naar VB-CABLE. Het venster zit apart in `app/vensters`. Daardoor kunnen we de audiocode later vanuit het HTML-dashboard aanroepen.
8. Iedere gestartte afspeelbeurt schrijft `geluid_gestart` en `geluid_gestopt`, inclusief bestandsnaam, afspeelbeurt-id, geplande duur, aangeleverde duur, daadwerkelijke verstreken tijd, stopreden en bufferproblemen. Fouten krijgen een volledige traceback.
9. **Nog uit te voeren op Windows:** update installeren, 45 tests draaien en de echte WAV-test uitvoeren volgens `FASE1B_TESTEN.md`.

**Klaar als:** de Windows-test echte WAV-gegevens door CABLE Input aanbiedt en de afspeelbeurt controleerbaar is via auditlogs. Voor aantoonbaar ontvangen geluid via CABLE Output kan zo nodig een extra opnamecontrole worden gedaan. De Razer blijft de Windows-speaker.

### Fase 2. Microfoonmix, veilige schakelaar en herstel

1. Voeg continue opname van de Razer-microfoon toe.
2. Voeg ringbuffer en realtime mixer toe.
3. Bouw de drie standen: `VERBROKEN`, `ALLEEN_MICROFOON`, `SOUNDBOARD_ACTIEF`.
4. Bouw eerst de veilige overgang tussen `ALLEEN_MICROFOON` en `SOUNDBOARD_ACTIEF`, zonder de audiostream te sluiten.
5. Voeg verbroken-apparaat-detectie, herverbinden en statuslogs toe.
6. Test met CABLE Output als opnamebron dat de stem blijft doorgaan als geluidseffecten uitstaan.

**Klaar als:** er nooit een lege CABLE-stream ontstaat bij alleen het uitschakelen van effecten.

### Fase 3. Moderne desktopinterface

1. Voeg pywebview toe en maak HTML/CSS/JS voor het dashboard.
2. Toon de drie verbindingsstanden, microfoonkeuze en één testgeluidskaart.
3. Voeg veilige JS-Python-koppelingen toe met expliciete parametervalidatie.
4. Maak de app met een dubbelklik startbaar en zonder zichtbare console in de productiebuild.
5. Voeg statusmeldingen toe die naar concrete foutcodes en de logmap verwijzen.

**Klaar als:** de gebruiker zonder terminal de microfoonmix bedient.

### Fase 4. Bibliotheek en media

1. Voeg SQLite toe en implementeer toevoegen, hernoemen en verwijderen.
2. Voeg categorieën, zoeken, favorieten en volume per fragment toe.
3. Voeg afbeeldingen, GIF's en MP4-thumbnails toe.
4. Voeg optionele audio-importconversie en beheerde bestandsopslag toe.
5. Voeg bibliotheekexport en import met manifest toe.

**Klaar als:** ingevoerde geluiden en afbeeldingen bij herstart terugkomen.

### Fase 5. Geluidskwaliteit, apparatenprofielen en snelheid

1. Controleer verschillen in samplefrequentie en kanaalaantallen.
2. Test gelijktijdige fragmenten, limiter en lokale monitor.
3. Voeg Razer en AirPods-profielen toe met veilige fallback.
4. Test langdurig onder gamebelasting en met USB- en Bluetooth-wisselingen.
5. Controleer prestatietellers en logrotatie onder belasting.

**Klaar als:** geen hoorbare fouten bij normale belasting en begrijpelijke herstelopties bij uitval.

### Fase 6. Integratie met Discord en WhatsApp op Windows

1. Selecteer in Discord `CABLE Output` als Input Device en de Razer als Output Device.
2. Test met en zonder Discord-noise suppression / Krisp.
3. Test `SOUNDBOARD_ACTIEF`, daarna `ALLEEN_MICROFOON`, daarna bewust `VERBROKEN`.
4. Doe dezelfde tests met WhatsApp Desktop, voor zover de gebruikte versie een microfoon laat selecteren. Anders gebruikt die mogelijk de Windows-standaardinvoer.
5. Vraag een tweede persoon hoe hoorbaar stem en effecten zijn. De belapp kan het geluid comprimeren of filteren.

**Klaar als:** de andere deelnemer daadwerkelijk beide bronnen hoort en de schakelaars voorspelbaar werken.

### Fase 7. Installer en bruikbaarheid op andere pc's

1. Bouw met PyInstaller een Windows-mapbuild van de app inclusief Python-runtime en benodigde modules.
2. Maak een installer met Inno Setup met snelkoppeling, versie, uninstall en reparatie-instructies.
3. Detecteer bij eerste start WebView2, VB-CABLE en audioapparaten. Toon wat ontbreekt; voer geen stille driverinstallaties uit.
4. Zet gegevens en logs buiten de programmamap; verwijder gebruikersbibliotheken niet automatisch bij uninstall.
5. Test op een schone Windows 11 x64-pc zonder Python of ontwikkeltools.
6. Publiceer versienummer, changelog, documentatie en een installatiehandleiding. Beoordeel ondertekening om SmartScreen-waarschuwingen te beperken.

**Klaar als:** een tester op een schone, ondersteunde Windows-pc de app kan installeren en openen zonder Python te installeren. Externe drivers kunnen wel apart nodig zijn en hebben mogelijk beheerdersrechten en een herstart nodig.

### Fase 8. Oplevering

1. Voer alle tests uit, inclusief fouten door missende/lege/extra parameters.
2. Controleer audit-events van gelijktijdig afspelen en voortijdig stoppen.
3. Maak het diagnosepakket en test of privégegevens worden afgeschermd.
4. Werk README, INSTALLEREN en CONTRIBUTING bij.
5. Controleer vereiste licenties en voer een echte uninstalltest uit.

## 9. Acceptatietests die echt uitgevoerd moeten worden

| Test | Verwacht resultaat |
| --- | --- |
| Soundboard uit tijdens actief gesprek | Stem blijft hoorbaar zonder geluidseffecten. |
| Soundboard aan, geluid starten en na 1 s stoppen | Geluid stopt en audit bevat werkelijke afspeelduur en stopreden. |
| Volledige verbinding verbreken | Streams sluiten, app zegt dat CABLE Output stil is. |
| Razer USB loskoppelen | App meldt exact welk apparaat ontbreekt; geen crash zonder log. |
| AirPods wisselen | App probeert gekozen bron en toont beperking/fout als die niet beschikbaar is. |
| VB-CABLE ontbreekt | App start in bibliotheekmodus en toont installatie-instructie. |
| Een functie krijgt een extra of lege parameter | Actie wordt afgewezen met foutcode; softwarelog bevat verwachte en ontvangen gegevens en traceback als een exceptie is ontstaan. |
| Beschadigd audiobestand | Geen crash van hele app; fout met bestandidentificatie en oorzaak. |
| Onverwachte exception | Traceback, sessie-id, component, oorspronkelijke fout en foutcode staan in log. |
| Twee geluiden tegelijk | Elke afspeelbeurt eigen `afspeelbeurt_id`, start en stop. |
| App afsluiten en opnieuw starten | Bibliotheek, profielen en loghistorie blijven aanwezig. |
| Schone Windows 11 x64 | Installer werkt zonder lokaal aanwezige Python. |

## 10. Bronnen en aanvullende instructies

Lees naast dit plan ook `INSTALLEREN.md`, `CONTRIBUTING.md` en `README.md`. Officiële technische referenties:

- VB-CABLE: https://vb-audio.com/Cable/
- Python voor Windows: https://www.python.org/downloads/windows/
- Python `sounddevice`: https://python-sounddevice.readthedocs.io/
- pywebview installatie: https://pywebview.idepy.com/en/guide/installation
- Microsoft WebView2 distributie: https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution
- Windows microfoontoegang: https://support.microsoft.com/nl-nl/windows/privacy/turn-on-app-permissions-for-your-microphone-in-windows
- Discord geluidsinstellingen: https://support.discord.com/hc/en-us/articles/360045138471-Discord-Voice-and-Video-Troubleshooting-Guide
- PyInstaller: https://pyinstaller.org/
- Inno Setup: https://jrsoftware.org/isinfo.php


## Tussenfase: microfoon en VB-CABLE signaaldiagnose (fase 2.1)

Tijdens de eerste praktijktest van fase 2 gaf DrostSoundboard `Verbonden` aan, maar was er volgens de gebruiker geen hoorbaar geluid. De status was gebaseerd op het starten van de PortAudio-stream en bevatte nog geen signaalmeting.

De diagnose-update voegt toe: live RMS-metingen van microfooningang en aangeboden kabeluitgang, callback- en frametellers, automatische detectie van een vastgelopen callback, technische niveaulogs met tussenpozen van vijf seconden, een rechtstreekse Razer-microfoontest zonder opslag van opnames en een handleiding om de uitkomst te interpreteren.

**Acceptatiecriterium:** met spraak op de Razer zien we een RMS-niveau bij microfoon en aangeboden kabelsignaal. Daarna controleren we met de Windows-opnamemeter bij `CABLE Output` dat de virtuele driver dat signaal daadwerkelijk doorgeeft. Pas als dat is bevestigd, zetten we Discord op de virtuele microfoon.

Als een microfoon direct werkt maar niet met de WASAPI-duplexstream, wordt een audioengine met aparte input- en outputstreams en buffering de eerstvolgende technische mijlpaal. Deze verandering vereist speciale tests op klokdrift en vertraging.


## Diagnosefase 2.3: WAV-overdracht helemaal tot CABLE Output bewijzen

- [x] Loggergegevens en de werkelijke audiomix vergelijken.
- [x] Vaststellen dat het achtsecondenvoorbeeld grotendeels stil is en laag wordt afgespeeld.
- [x] Een continue controletoon van twaalf seconden toevoegen.
- [x] De herkenning van een 660 Hz-signaal onafhankelijk van de microfoon bouwen.
- [x] Een opnamecontrole voor CABLE Output met eigen audit- en softwarelogs toevoegen.
- [x] Automatische tests voor signaalherkenning en een nagebootste opnamekant uitvoeren.
- [ ] Op de echte Windows-computer het resultaat van de opnamecontrole verifiëren.
- [ ] Als ontvangst is bevestigd: Discord en WhatsApp testen met CABLE Output als microfoon.
- [ ] Als ontvangst niet is bevestigd: apparaatformaten, kanaalkeuze en onafhankelijke streams onderzoeken.

Deze diagnose verandert niets aan de bestaande verbinding die de echte
Razer-microfoon doorgeeft. Aanpassingen aan de live-mixer doen we pas wanneer
het onafhankelijke meetresultaat aantoont waar het geluidsfragment wegvalt.

## Voortgang 23 oktober 2026: fase 2.3 bevestigd en fase 2.4 toegevoegd

**Bevestigd op echte Windows-hardware:** `Meet_CABLE_Output.bat` registreerde de 660 Hz-controletoon op de opnamekant van VB-CABLE, hoogste RMS 0,10439, hoogste piek 0,14700, 62 blokken met de toon en nul bufferproblemen. De 103 automatische tests van fase 2.3 slaagden ook op de ontwikkelcomputer. De volledige weg van DrostSoundboard tot VB-CABLE is daarmee aangetoond. Discord en WhatsApp moeten nog afzonderlijk worden getest.

**Fase 2.4 in de broncode toegevoegd:** ondersteuning voor MP3 en WAV met `soundfile`; hoge-kwaliteit omzetting met `soxr`; voorbereiding in een achtergrondthread; fragmentstartpunt; limiet van 45 seconden per afspeelbeurt; SQLite met eigen namen en een lijst met meerdere geluiden. Dit is nog het tijdelijke Windows-venster. De echte MP3-bestanden van de gebruiker zijn niet bij de ontwikkelomgeving gevoegd en moeten lokaal in de app geselecteerd worden.

**Gewijzigde bibliotheekstrategie tijdens deze ontwikkelfase:** een nieuw item bewaart alleen het bestaande pad en de zelfgekozen naam in SQLite, zonder de bronbestanden te kopiëren. De toekomstige definitieve bibliotheek krijgt de eerder geplande optie voor beheerde kopieën en export, zodat verplaatsen naar een andere Windows-pc betrouwbaar werkt. Bestandslocaties in Downloads zijn dus voorlopig een afhankelijkheid die in de interface en handleiding duidelijk moet worden uitgelegd.

**Nog te realiseren:** volledige audiostreaming van minutenlange nummers zonder groot RAM-gebruik, individuele volumeregelaars, afbeeldingen/animaties, HTML/CSS/JavaScript-dashboard, veilige installer inclusief noodzakelijke audiocomponenten, migratie/backup van bibliotheek en gebruikersvriendelijke herstelfuncties. De tests met echte audio in Discord/WhatsApp en AirPods horen daar ook bij.

Zie `FASE2_MP3_BIBLIOTHEEK_TESTEN.md` voor de concrete Windows-stappen. De bestaande geluidsrouting wordt in fase 2.4 niet gewijzigd; zo blijft de eerder bewezen VB-CABLE-route behouden.

# Aanvulling fase 3: lokale webinterface, favorieten en echte gesprekstest

De eerdere fases hebben aangetoond dat de eigen Razer-microfoon en de 660 Hz-controletoon op de virtuele opnamekant van VB-CABLE aankomen. We vervangen nu de tijdelijke Tkinter-interface door een lokale, responsieve webpagina. Python blijft de realtime audiomixer draaien. Dit maakt de vormgeving flexibeler, maar garandeert op zichzelf geen foutloze Windows-audio.

De nieuwe webversie levert vijftien vaste favorietplekken met blijvende nummering, een bibliotheek voor MP3 en WAV, een startpunt en een maximale duur van 120 seconden per geluid, een volume-instelling, afbeelding en GIF als thumbnail, verbindingsknoppen, live niveaumeters en gescheiden audit- en softwarelogging. Het raster schaalt met de schermbreedte, terwijl de volgorde in SQLite gelijk blijft.

De bestanden die via de browser worden toegevoegd, worden lokaal gekopieerd. Zo blijven geluidskaarten werken wanneer iemand het origineel uit Downloads verwijdert. De eerdere bibliotheek met bestandspaden blijft ondersteund. Video-preview met MP4 komt in een volgende fase. Voor volledige muziekstreaming zonder lange voorbereidingsbuffer is later aanvullende audio-engineering nodig.

## Belangrijkste kwaliteitsproef voor de volgende fase

Een geslaagde onafhankelijke CABLE Output-meting toont aan dat Python en de driver de geluiden doorgeven, maar nog niet dat een andere deelnemer ze in Discord of WhatsApp ontvangt. Daarom hoort een echte beltest bij de acceptatie: Discord gebruikt `CABLE Output` als invoerapparaat, Razer blijft geselecteerd als uitvoer, spraakactiviteit staat aan en muziekfiltering wordt tijdens de test tijdelijk uitgeschakeld. Eerst komt een microfoontest, daarna een gesprek met een vrijwillige testpartner.

## Beslispunt voor de definitieve installer

De broncodeversie vereist nog Python 3.13. De uiteindelijke EXE-installer wordt pas als aparte fase gebouwd nadat de lokale webinterface, het apparaatwisselen, de signalen bij de andere partij en de logboeken op Windows geslaagd zijn. De installer moet de benodigde Python-runtime meeleveren, de externe VB-CABLE-driverstatus controleren en een herstelpad bieden. Elke volgende wijziging mag de werkende audiomixer niet ongemerkt vervangen.

## Fase 4.0: moderne interface en multimedia

**Doel:** DrostSoundboard opent met een centraal geanimeerd logo. Het dashboard heeft vijftien onveranderlijk genummerde favoriete plekken, een grote Now Playing-weergave en een aparte bibliotheek met Preview-knoppen.

**Audiostromen:** preview gebruikt uitsluitend browserweergave. Live geluid loopt via Python naar VB-CABLE. Optioneel gaat alleen het effect ook naar een gekozen headset via een onafhankelijke WASAPI-monitorwerkdraad. De fysieke microfoon wordt nooit lokaal gemonitord. Een uitgevallen headsetmonitor mag geen werkende microfoonverbinding onderbreken.

**Video:** de bron-MP4 blijft behouden en wordt lokaal via HTTP Range aan het gedempte HTML5-video-element geleverd. FFmpeg decodeert alleen maximaal 120 seconden audio naar de mixer. De bibliotheek bewaart de gekozen beeldvoorkeur. Een zelfgekozen GIF/photo kan het videobeeld overrulen. Video en animaties stoppen wanneer de audiomixer klaar is.

**Veiligheid:** uploads blijven beperkt tot toegestane extensies, afmetingen en formaten. MP4 moet audio en video bevatten. Paden blijven aan lokale beheerde bestanden gekoppeld en bestandsnamen worden nooit als shellcommando uitgevoerd. Geen internetdienst, cloudprofielen of ongecontroleerde externe scripts.

**Aanvullende testcriteria:** een echte MP4 met H.264/AAC, een GIF met statische miniatuur, live stop versus natuurlijk einde, preview die nooit de mixer aanroept, monitor zonder microfoon, migratie van een oudere SQLite-bibliotheek en HTTP Range voor videoseeken.

**Nog open:** verificatie met Razer en AirPods op Windows, end-to-end Discord/WhatsApp audio, prestatiemeting tijdens gamen, en een zelfstandige Windows-installer inclusief aandacht voor licenties en betrouwbare driverinstallatie.

## Fase 5, oktober 2026: dashboard, groepen en tijdlijneditor

- [x] Nieuwe donkere, responsieve webinterface zonder frontend-framework
- [x] Werkelijke bronduur bepalen en maximaal twee minuten van de bron gebruiken
- [x] 15 vaste favoriete posities behouden
- [x] Vrije groepen met eigen namen, meervoudig lidmaatschap en filters
- [x] Fragmentselectie met begin- en eindmarkering, golfvorm en lokaal beluisteren
- [x] MP4-videoposter maken voor lichte bibliotheekweergave
- [x] Auditlogging van groepswijzigingen en softwarelogging van browserfouten
- [x] Automatische regressietests zonder benodigde audiohardware
- [ ] Live test op Windows 11 met Razer, VB-CABLE en een echt Discordgesprek
- [ ] Onafhankelijke, ondertekende Windows-installer en herstel bij ontbrekende drivers

De fragmenteditor is niet-destructief. Het oorspronkelijke MP3-, WAV- of MP4-bestand blijft volledig staan. Bij een bestand van 29 seconden toont de webinterface `0:29`, ook als de algemene tijdslimiet `2:00` is. Een groepslidmaatschap wordt atomair opgeslagen en mag niet tot dubbele mediaopslag leiden.

## Fase 5.5 | Precisiemodus en grotere bibliotheek (ontwikkelupdate)

- [x] Begin en einde op drie decimalen instelbaar, maximum 120 seconden.
- [x] Zoomvenster met knopbediening, horizontaal scrollen en langdruk op selectiegrenzen.
- [x] Meer golfvormdetail bij zoom, zonder de realtime audiomixer te belasten.
- [x] Extra SQLite-metadata: beschrijving, gesproken tekst en zoekwoorden.
- [x] Doorzoekbare grote bibliotheekweergave met gefaseerde lijstweergave.
- [x] Meerdere geluiden tegelijk aan groepen koppelen of uit bibliotheek halen.
- [x] Draagbare ZIP-export/import met originele media en instellingen, met expliciete beperkingen en veiligheidstests.
- [ ] Realtime sampleprecieze preview in alle browsers en voor iedere codec is niet gegarandeerd.
- [ ] Een afzonderlijk geknipt WAV/MP3 exporteren is een mogelijke latere functie.

Geen aanpassing aan de Razer-microfoon, VB-CABLE-configuratie of de PortAudio-callback.

### Versie 5.6: losse media-export

Losse downloadkeuze voor MP3, MP4 en GIF toegevoegd. De audiotrack, het
videobeeld en een gekoppelde GIF zijn gescheiden bestanden. Een opgeslagen
fragment wordt ook afzonderlijk als MP3 gedownload; vanuit de fragmenteditor
kunnen nog niet opgeslagen begin- en eindtijden worden gekozen. De bestaande
ZIP-bibliotheekexport blijft beschikbaar. Conversies zijn begrensd en
worden buiten de realtime mixer afgehandeld. Voor technische afspraken:
`FASE5_6_LOSSE_MEDIA_EXPORTEREN.md`.
