# Fase 1: de eerste echte VB-CABLE-test

**Status:** de Python-code en automatische unit-tests zijn voorbereid. De test op de echte Windows-geluidsapparaten moet nog plaatsvinden.

## Wat we gaan controleren

De test stuurt gedurende 1,8 seconde een zachte toon van 440 Hz met 48.000 samples per seconde naar de gewone **CABLE Input**. Tegelijkertijd wordt de **CABLE Output** ongeveer 3,2 seconde gemeten. De test controleert of het virtuele opnameapparaat een bruikbaar signaal heeft ontvangen en of daarin juist de bedoelde toon van 440 Hz herkenbaar is.

Dit is nog geen geluidenmixer, dashboard of microfoondoorgifte. De echte Razer-microfoon wordt niet geopend. De test verandert niets aan de standaard Windows-luidspreker of standaardmicrofoon en schrijft geen opgenomen audio naar schijf.

**Doe de kabeltest bij voorkeur niet tijdens een Discord- of WhatsApp-gesprek.** Als een belapp nu al CABLE Output gebruikt, kan een gesprekspartner de testtoon horen.

## Stap 1. Installeer deze update op je bestaande project

Deze ZIP bevat alleen nieuwe of bijgewerkte projectbestanden, niet je `.venv`. De installatie van Python en `sounddevice` is eerder al geslaagd.

Ga in PowerShell naar de map waarin je projecten staan:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"
```

Download `DrostSoundboard_Fase1_Update.zip` en voer uit:

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase1_Update.zip" -DestinationPath . -Force
```

**Let op:** dit gaat ervan uit dat het ZIP-bestand in Downloads staat. Als je zelf de documentatie of `logboek.py` hebt gewijzigd, maak daarvan eerst een kopie, want de bestanden die in deze update zitten worden vervangen. De bestaande `.venv`, je andere projectbestanden, de apparaatcontrole en de bestanden in `%LOCALAPPDATA%` worden niet vervangen.

## Stap 2. Controleer of de update goed is uitgepakt

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects\DrostSoundboard"
Get-ChildItem -Name
```

Hier moet onder andere het nieuwe `Test_Virtuele_Kabel.bat` staan. De oorspronkelijke `Start_DrostSoundboard.bat` blijft ook werken.

## Stap 3. Test de Python-code

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

De nieuwe fase heeft 19 aanvullende tests. Samen met de zeven bestaande tests geeft dit 26 tests. Deze werken zonder fysieke audioapparaten.

## Stap 4. Voer de hardwaretest uit

Start vanuit de projectmap:

```powershell
.\Test_Virtuele_Kabel.bat
```

Het programma selecteert `CABLE Input` en `CABLE Output` met de **Windows WASAPI**-audio-API op naam. De eerder gevonden nummers 21 en 23 mogen na een herstart veranderen.

Het toont welke apparaten zijn gekozen, hoelang de toon duurde, hoeveel frames zijn gemeten, de signaalsterkte, de herkenning van de specifieke testtoon en eventuele bufferproblemen.

Bij voldoende signaal en zonder gedetecteerde bufferproblemen krijg je `GESLAAGD`. Dat betekent dat de virtuele kabel audio doorgeeft. Het garandeert nog niet dat Discord, WhatsApp of de Razer-microfoon al werkt.

## Stap 5. Controleer het auditlog en softwarelog

Open via:

```powershell
.\Open_Logboeken.bat
```

Of met Verkenner:

```text
%LOCALAPPDATA%\DrostSoundboard\logboeken
```

`audit.jsonl` krijgt gebeurtenissen zoals `kabeltest_gestart`, `geluid_gestart`, `geluid_gestopt` en `kabeltest_afgerond`. De gebeurtenissen voor het geluid bevatten een unieke afspeelbeurt-id, geluids-id, volume, aangeboden duur, resultaat en de gemeten verstreken tijd.

`software.jsonl` registreert de geselecteerde apparaten, gemeten niveaus en, bij een fout, de volledige Python-traceback inclusief de actie waar het misging. `crashes.txt` kan leeg zijn, en dat is normaal.

## Als het misgaat

| Wat je ziet | Wat je eerst controleert |
| --- | --- |
| `KABEL-002` | De gewone CABLE Input en Output zijn beschikbaar via WASAPI. We gebruiken niet CABLE In 16ch. |
| `KABEL-006` of `KABEL-007` | Een andere app gebruikt CABLE Output, Windows geeft geen opnametoegang of de driver reageert niet. |
| `KABEL-008` of `KABEL-009` | Het lezen van CABLE Output stokt. Open `software.jsonl` voor de volledige oorzaak. |
| `NOG NIET GOED` | CABLE Input krijgt te weinig signaal of de audiostream had bufferproblemen. Controleer VB-CABLE-volumes in `mmsys.cpl`. |
| Een PortAudio-fout over samplefrequentie | Controleer in `mmsys.cpl` bij beide VB-CABLE-eindpunten of een normale 48.000 Hz-configuratie beschikbaar is. Verander niet willekeurig je Razer-instellingen. |
| `ModuleNotFoundError: sounddevice` | Voer opnieuw `Installeer_ontwikkelomgeving.bat` uit. |

**Graag terugsturen:** de PowerShell-uitvoer van `Test_Virtuele_Kabel.bat`. Bij een fout zijn ook de nieuwe regels uit `software.jsonl` nuttig. Deel nooit complete logbestanden zonder eerst te controleren op privégegevens.

## Hierna

Als deze test op Windows slaagt, voegen we het afspelen van een echt geluidsbestand toe. Daarna bouwen we de audiomixer met de Razer-microfoon en de knop voor `Soundboard aan`, `Soundboard uit` en `Verbinding verbreken`.
