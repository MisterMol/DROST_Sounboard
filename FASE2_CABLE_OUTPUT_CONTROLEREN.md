# DrostSoundboard: ontvang ik mijn WAV echt bij CABLE Output?

## Wat we zeker weten

De microfoon komt bij VB-CABLE aan en de Python-mixer mengt de WAV in zijn uitvoerbuffer. Maar de twee meters in het bestaande venster bewijzen niet dat het andere uiteinde van de kabel precies die WAV ontvangt.

De oude `voorbeeld_lang_8seconden.wav` heeft vijf korte tonen met lange stille stukken. De applicatie speelt die bovendien op 35% signaalamplitude af. Daarom kan de Windows-niveaumeter tijdens de stiltes niets tonen. Dit is niet hetzelfde als bewijzen dat de hele verbinding stuk is.

Deze update bevat een **nieuwe, continue controletoon van 12 seconden** en een **onafhankelijke opnamecontrole** voor CABLE Output. De opnamecontrole opent de Razer-microfoon niet en stuurt ook niets naar CABLE Input. Hij controleert alleen wat een ander programma via de virtuele microfoon kan opnemen. Er worden geen audio-opnames opgeslagen.

## Stap 1. Sluit de applicatie en installeer de update

Open PowerShell in `C:\Users\jelle\Desktop\pythonProjects` en maak eerst een back-up. Deze back-up bevat alleen broncode, niet de `.venv`.

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"
Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.py,.\DrostSoundboard\*.bat,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_cable_meting.zip -Force
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase2_Cable_Meting_Update.zip" -DestinationPath . -Force
cd .\DrostSoundboard
```

## Stap 2. Test de software

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Er horen **103 tests** te slagen. Je hoeft geen nieuwe Python-pakketten te installeren.

## Stap 3. Start het soundboard

```powershell
.\Start_DrostSoundboard.bat
```

Klik op **Verbinden** en vink **Soundboard aan** aan. Het nieuwe bestand `controletoon_12seconden.wav` is nu standaard geselecteerd. Als je nog een ander bestand ziet, kies via **Kies WAV** dit bestand uit de map `voorbeelden`.

Laat het venster open en klik nog niet op afspelen.

## Stap 4. Meet de virtuele microfoon onafhankelijk

Open **een tweede PowerShell-venster** in dezelfde projectmap en voer uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects\DrostSoundboard"
.\Meet_CABLE_Output.bat
```

De meetfunctie vraagt je op Enter te drukken. Klik na Enter in het soundboard binnen enkele seconden op **Geluid afspelen**. Je hebt 20 seconden om het signaal te meten. De controletoon duurt 12 seconden.

De meetfunctie schrijft elke seconde een signaalniveau en vertelt aan het eind of de **660 Hz-controletoon** op `CABLE Output` is herkend.

### Zo interpreteer je het resultaat

| Uitslag | Wat het echt bewijst | Volgende stap |
| --- | --- | --- |
| **GESLAAGD: controletoon ontvangen** | Een tweede programma ontvangt de WAV via CABLE Output | Test de virtuele microfoon in Discord of WhatsApp; stel daar CABLE Output in |
| **Er is geluid, maar niet de controletoon** | Er komt audio binnen, maar de gekozen testtoon is niet betrouwbaar herkend | Controleer of je het nieuwe 12-secondenbestand echt afspeelde; herhaal één keer |
| **Geen bruikbaar signaal** | Tijdens de meting kwam onvoldoende niveau bij CABLE Output aan | Controleer de status van beide meters in de live-mixer en stuur de logboeken mee |
| **FOUT** | De afzonderlijke opnamekant kon niet worden geopend of gelezen | Bekijk de volledige traceback in de nieuwe ontvangstmeting-logmap |

Het Windows-niveaumetertje onder `mmsys.cpl > Opnemen` is slechts een indicatie. De aparte opnamecontrole geeft een veel bruikbaarder resultaat.

## Belangrijk voor je logbestanden

Omdat het live-mixervenster én de ontvangstcontrole tegelijk draaien, gebruiken ze **verschillende logbestanden**. Dat voorkomt problemen met twee processen die hetzelfde bestand tegelijk proberen te roteren.

- Het soundboard blijft loggen onder `%LOCALAPPDATA%\DrostSoundboard\logboeken`.
- Iedere ontvangstmeting krijgt een eigen map onder `%LOCALAPPDATA%\DrostSoundboard\logboeken\ontvangstmetingen\<testnummer>`.

Stuur bij een mislukte meting de **laatste** `software.jsonl` en `audit.jsonl` uit die submap. Daarin staan de originele tracebacks en alle meetwaarden. Audio en spraak worden niet opgeslagen.

## Dit moet je nog niet veranderen

Verander je standaard microfoon, Windows-uitvoer en Discord-instellingen nu nog niet. Installeer VB-CABLE niet opnieuw: de eerdere aparte kabeltest en je werkende microfoonverbinding tonen dat de driver functioneert. We verhelpen eerst de onzekerheid over de daadwerkelijke WAV-overdracht.
