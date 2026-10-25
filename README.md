# DrostSoundboard

Open-source soundboard voor Windows 11. Speel MP3, WAV en MP4 af via een bestaande virtuele microfoon en houd je headset beschikbaar om zelf mee te luisteren. Het lokale webdashboard is alleen de bediening; het Windows-systeemvakproces blijft actief als de browser dichtgaat.

**Status: 6.0.0-beta.3, nog niet publiek uitgebracht.** De zelfstandige Windows-installer is in ontwikkeling; installatie en automatische updates moeten op een tweede computer worden getest.

## Wat kan het?

- 15 vaste favorieten, groepen, zoekfunctie, fragmenteditor en audiopreview.
- Audiofragmenten van maximaal 120 seconden, met eigen afbeelding, GIF of MP4-beeld.
- Microfoon met effecten mixen via VB-CABLE; eigen headset kan meeluisteren.
- Globale sneltoetsen (optioneel, standaard uit) en Windows-systeemvak.
- Thema's, afspeelgeschiedenis en aparte exports als MP3, MP4, GIF en afbeelding.
- Gescheiden auditlog en technische logging met tracebacks.

## VB-CABLE is een afzonderlijke installatie

**[Download VB-CABLE via VB-Audio](https://vb-audio.com/Cable/)**. Deze donationware-driver wordt niet door DrostSoundboard meegeleverd. Na installatie en eventuele Windows-herstart:

| Waar | Apparaat |
| --- | --- |
| Microfooningang van DrostSoundboard | Je Windows-standaardmicrofoon of een zelfgekozen microfoon |
| Uitvoer van de audiomixer | `CABLE Input` |
| Virtuele microfoon in andere programma's | `CABLE Output` |
| Lokaal meeluisteren | Je Windows-standaarduitvoer of een zelfgekozen luisterapparaat |

Let op: als DrostSoundboard helemaal stopt, kan je virtuele microfoon stilvallen. Zet dan eventueel de echte microfoon in je belapp terug.

## Ontwikkelinstallatie (Windows 11)

1. Installeer Python 3.13 en VB-CABLE afzonderlijk.
2. Pak of kloon de projectcode uit naar een zelfgekozen map.
3. Dubbelklik één keer op `Installeer_ontwikkelomgeving.bat`.
4. Maak de bureaubladsnelkoppeling met `Maak_Bureaublad_Snelkoppeling.bat` en start daarna via die snelkoppeling.
5. Kies in het dashboard je microfoon, klik op **Verbinden** en schakel **Geluidseffecten** aan.
6. Stel globale sneltoetsen zo nodig in via **Sneltoetsen**.

Een browser sluiten beëindigt het systeemvakproces niet. Gebruik **Afsluiten** in het systeemvak om de volledige app te stoppen.

## Testen en problemen melden

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects\DrostSoundboard"
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

De tests gebruiken waar mogelijk nagebootste audioapparaten. **Ze bewijzen niet dat elke Windows-driver of game op elke pc werkt.** Gebruik bij fouten `Start_DrostSoundboard_Ontwikkeling.bat` en kijk onder `%LOCALAPPDATA%\DrostSoundboard\logboeken` naar `software.jsonl` en `audit.jsonl`.

Bij een onverwachte API-fout toont de browser een korte **logreferentie**. Zoek die terug in `software.jsonl` voor de echte Python-traceback. Deel bij GitHub-issues geen volledige privébestanden of niet-geanonimiseerde logs.

### MP4 vanaf 5.9.4

Het dashboard maakt bij een live MP4 nog maar één videospeler aan, start pas na het zoeken naar het juiste fragment en corrigeert kleinere verschillen zonder telkens het beeld terug te zetten. Python bepaalt het hoorbare geluid; de browser toont gedempt beeld. De feitelijke vloeiendheid is mede afhankelijk van codec en systeem.

## Ontwikkelen en bijdragen

Lees [`ARCHITECTUUR.md`](ARCHITECTUUR.md) voor een modulekaart, [`CONTRIBUTING.md`](CONTRIBUTING.md) voor code-afspraken en [`SECURITY.md`](SECURITY.md) voor beveiligingsmeldingen. Versiegeschiedenis en oudere fasehandleidingen zijn referentiemateriaal, niet de huidige installatie-instructie.

De eigen code valt onder [`LICENSE`](LICENSE) (MIT). Externe bibliotheken behouden hun eigen licenties; zie [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Controleer vooral FFmpeg en andere gebundelde onderdelen vóór publicatie van een Windows-installer.

Repository: https://github.com/MisterMol/DROST_Sounboard

## VB-CABLE controleren bij de eerste start

DrostSoundboard controleert in het dashboard of beide kanten van de gewone VB-CABLE via Windows WASAPI zichtbaar zijn. Als de kabel ontbreekt of niet volledig beschikbaar is, verschijnt een rustige melding met een link naar de [officiële VB-Audio-download](https://vb-audio.com/Cable/) en **Opnieuw controleren**. De geluidsbibliotheek en lokale previews werken zonder VB-CABLE; een virtuele microfoon voor games of gesprekken niet. VB-CABLE blijft een aparte driverinstallatie en wordt nooit stilzwijgend geïnstalleerd. Zie `FASE6_0_BETA2_VB_CABLE_CHECK.md`.
