# Versie 5.9: desktop, systeemvak en globale sneltoetsen

## Doel

Het dashboard wordt een bedieningsscherm, niet de eigenaar van het audioproces. Sluit je de browser, dan blijft de audiomixer actief totdat je via het systeemvak echt afsluit.

## Eenmalig installeren

In PowerShell, in de DrostSoundboard-map:

```powershell
.\Installeer_ontwikkelomgeving.bat
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

## Gewoon starten

Dubbelklik `Start_DrostSoundboard.bat`. Er verschijnt geen blijvend terminalvenster. Binnen Windows verschijnt een DrostSoundboard-pictogram in het systeemvak, zo nodig onder het pijltje met verborgen pictogrammen.

1. Kies in het dashboard je microfoon en klik **Verbinden**.
2. Sluit je browsertabblad. In Discord mag de microfoon op CABLE Output blijven staan.
3. Open het systeemvakmenu met een rechtermuisklik. **Dashboard openen** toont hetzelfde dashboard.
4. **Alle geluiden stoppen** stopt alleen het geluidseffect. Je microfoon blijft verbonden.
5. Klik **Afsluiten** om de audiomixer, HTTP-server en sneltoetsen echt te stoppen.

**Let op:** zolang DrostSoundboard gesloten is, ontvang je geen fysieke microfoon meer via CABLE Output. Zet desgewenst je microfooninstelling in de belapp terug naar je eigen microfoon.

## Sneltoetsen testen

Open **Sneltoetsen** boven in de webpagina. Zet de schakelaar aan, klik in een invoerveld en druk bijvoorbeeld Ctrl + Alt + 1. Sla op. Speel vervolgens het bijbehorende favorietgeluid terwijl de game actief is. Met de eigen Stop-combinatie stopt het fragment. Krijg je een melding dat Windows de combinatie niet kan registreren, kies dan een andere.

Sneltoetsen zijn optioneel en staan standaard uit. De webpagina hoeft na configureren niet open te blijven.

## Fouten herkennen

| Probleem | Controle |
|---|---|
| Geen systeemvakicoon | Open verborgen pictogrammen. Controleer `software.jsonl`; controleer installatie van `pystray`. |
| Geen audio na sluiten browser | Controleer of het systeemvakproces nog draait en DrostSoundboard verbonden is. |
| Tweede dubbelklik maakt geen nieuw proces | Correct. De bestaande webpagina moet openen. |
| Sneltoets doet niets | Controleer dat sneltoetsen aanstaan, dat de favoriet gevuld is en er geen registratieconflict is. |
| Geen stem via VB-CABLE na Afsluiten | Correct. De audiomixer stopt bij volledig afsluiten. |
| Sneltoets werkt in Discord maar niet in een game | Sommige games of anti-cheats beperken globale combinaties. Dit kunnen we niet omzeilen of garanderen. |

## Veiligheid en technische keuzes

- `RegisterHotKey` in een aparte Windows-thread, **geen toetsenbordhook**.
- Geen process-injectie, overlays, administratorrechten of wijzigingen aan gamebestanden.
- Windows-mutex voorkomt dubbele audiomixers binnen dezelfde interactieve sessie.
- HTTP uitsluitend op `127.0.0.1`, met sessietoken en herkomstcontrole voor schrijfacties.
- Alle fouten inclusief traceback naar logboeken in LOCALAPPDATA.
- VB-CABLE zelf wordt niet meegeleverd. [Officieel VB-CABLE](https://vb-audio.com/Cable/).
- Voorkeuren worden lokaal bewaard; geen automatische opstart bij Windows zonder opt-in.

## Openstaande Windows-tests

Deze patch is op de code en in automatische tests gecontroleerd. Specifieke Win32-gedragingen moeten op Windows 11 worden bevestigd: mutex bij dubbele start, pystray-menu, hotkeyregistratie en vrijgave, gamecompatibiliteit en afhandeling van USB-verbindingen. Er is nog geen zelfstandige EXE of installer.
