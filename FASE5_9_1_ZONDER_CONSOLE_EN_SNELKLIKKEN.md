# DrostSoundboard 5.9.1: achtergrondstart en snelle knoppen

Deze correctie is bedoeld voor de bestaande versie 5.9. De audiomixer,
VB-CABLE-instellingen, groepen, favorieten, media en sneltoetsen blijven behouden.

## Wat is aangepast?

- Alle aanroepen van de meegeleverde FFmpeg-decoder krijgen op Windows de vlag `CREATE_NO_WINDOW`.
  Videocontrole, MP4-audio, miniaturen, golfvorm en export kunnen daardoor werken zonder losse CMD-vensters.
- De oorspronkelijke decoderuitvoer en traceback blijven bij echte fouten beschikbaar in `software.jsonl`.
- Een browser die bij stoppen of doorspoelen de MP4-verbinding verbreekt, veroorzaakt niet meer onnodig een HTTP 500.
- Gelijktijdige klikken op Verbinden of dezelfde schakelaar worden gedempt.
- De nieuwste afspeelopdracht krijgt voorrang boven oude wachtende decodeeropdrachten.
- Er is een eenmalig hulpmiddel om een bureaubladsnelkoppeling rechtstreeks naar `pythonw.exe` te maken.

## Veilig installeren

1. Sluit DrostSoundboard via het pictogram in het Windows-systeemvak, niet alleen via het browsertabblad.
2. Open PowerShell en maak een back-up en pak de update uit:

   ```powershell
   cd "$env:USERPROFILE\Desktop\pythonProjects"
   Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests -DestinationPath .\DrostSoundboard_backup_voor_591.zip -Force
   Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_5_9_1_Console_En_Knoppen_Update.zip" -DestinationPath . -Force
   cd .\DrostSoundboard
   ```

3. Test:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -q
   ```

   Verwacht **289 tests**. Op Windows kunnen de bestaande platformspecifieke
   tests nog steeds worden overgeslagen. `OK` is belangrijker dan het aantal overgeslagen tests.

4. Maak de snelkoppeling **één keer**:

   ```powershell
   .\Maak_Bureaublad_Snelkoppeling.bat
   ```

   Het eenmalige hulpprogramma gebruikt wel een kort opdrachtpromptvenster.
   De aangemaakte snelkoppeling **DrostSoundboard** op het bureaublad start
   daarna direct `pythonw.exe`, zonder PowerShell of batchvenster.

5. Dubbelklik op het **nieuwe bureaubladpictogram**. Start voortaan niet meer met
   de `.bat` wanneer je volledig zonder CMD-flits wilt werken.

6. Probeer een MP4-preview, speel een ander geluid af en stop weer. De browser
   en de videodecoder moeten zonder losse consolevensters werken.

## Als er nog iets fout gaat

Open via het Windows-systeemvak **Logboeken openen** en controleer:

- `software.jsonl` voor de Python-fout en originele traceback
- `audit.jsonl` voor afspeel-, verbindings- en stopgebeurtenissen

Een browser die een oude mediaoverdracht annuleert kan als informatiegebeurtenis
`media_verzoek_door_browser_geannuleerd` verschijnen. Dat is niet hetzelfde als
het uitvallen van de audiomixer.

## Beperkingen

De Linux-tests simuleren de Windows-consolevlag. De werkelijke Windows-snelkoppeling,
FFmpeg-afhandeling en werking tijdens een game moeten op Windows 11 worden gecontroleerd.
Deze patch bevat **geen Windows-EXE-installer**. Die staat gepland voor versie 6.0.
