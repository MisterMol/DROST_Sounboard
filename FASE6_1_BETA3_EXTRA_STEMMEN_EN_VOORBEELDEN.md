# DrostSoundboard 6.1 Beta 3: extra stemmen en voorbeelden

Gebaseerd op de complete 6.1.0-beta.2-broncode. De bibliotheek en alle bestaande steminstellingen blijven behouden.

## Extra profielen

Jongensstem, Meisjesstem, Oudere man, Oudere vrouw, Xbox-lobby 2010 en Autotune (experimenteel). In totaal achttien profielen.

Dit zijn creatieve digitale stemfilters, geen natuurgetrouwe omzetting van geslacht, leeftijd of identiteit. Autotune is experimentele lokale nootcorrectie, geen professionele studioplugin.

## Extra parameters

Echo: vertraging 100 tot 1800 milliseconden, herhaling 0 tot 75 procent, effectmix 0 tot 100 procent. Autotune: toonsoort, toonladder (chromatisch/majeur/mineur) en correctiesnelheid.

Alle intensiteiten en speciale parameters worden per profiel in SQLite bewaard. Herstel dit profiel en Herstel alle profielen zetten de betreffende sterktes en effectparameters terug, zonder de bibliotheek te wijzigen.

## Meegeleverde stemvoorbeelden

- `app/audio/stemvoorbeelden/hello_my_name_is_bob.mp3`
- `app/audio/stemvoorbeelden/hello_my_name_is_elise.mp3`

Bob is standaard. Kies Bob of Elise, klik op een stemkaart en beluister de eigen opname via de browser met het gekozen filter. De knop Voorbeeld afspelen speelt opnieuw af nadat nieuwe instellingen zijn opgeslagen. De server verwerkt het originele MP3-bestand met dezelfde DSP als de live microfoon, en levert een tijdelijke WAV in geheugen. Er wordt niets naar de virtuele microfoon uitgezonden.

Mijn stem beluisteren blijft apart beschikbaar: daarvoor moet je de liveverbinding verbreken en je koptelefoon gebruiken.

## Bouw en licentie

Geen nieuwe runtimebibliotheken. `.gitignore` bevat uitzonderingen zodat precies deze twee MP3's wel op GitHub komen. PyInstaller bundelt beide MP3's en de EXE-smoketest controleert hun aanwezigheid. De releasebouwer ondersteunt nu 6.1.

Controleer zelf vóór openbare distributie of je de twee aangeleverde voorbeeldopnames mag herdistribueren.

De Windows-WASAPI-uitvoer en daadwerkelijke luisterkwaliteit moeten nog op fysieke apparatuur worden getest.
