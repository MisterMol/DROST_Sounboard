# DrostSoundboard 4.0: mooi dashboard, previews, video en meeluisteren

Dit document hoort bij **DrostSoundboard** op Windows 11. Je start nog steeds met één dubbelklik op `Start_DrostSoundboard.bat`. Geen extra commandoregelargumenten.

## Wat werkt in deze versie?

- Een centraal groot DrostSoundboard-logo bij het openen, daarna een korte fade naar het dashboard. Bij verminderde animaties in Windows wordt de splash overgeslagen.
- De 15 vaste favorietplekken blijven in dezelfde volgorde staan, ook wanneer het raster op een kleiner scherm verspringt.
- MP3, WAV en MP4 importeren. MP4 moet een audio- én een videospoor hebben.
- Via **Preview** beluister je het gekozen fragment alleen in je browser. Het gaat **niet** naar VB-CABLE.
- Via een geluidskaart **Afspelen** gaat het fragment naar de Python-mixer en VB-CABLE. Met **Zelf meeluisteren** aan gaat uitsluitend het geluidseffect ook naar je gekozen headsetuitgang. Je eigen stem wordt niet teruggespeeld.
- Tijdens het afspelen verschijnt de MP4-video (zonder dubbel geluid), een afbeelding of een geanimeerde GIF in het vlak **Now Playing**. Wanneer de audio stopt, verdwijnt het actieve beeld ook.
- Per geluid bepaal je de naam, de eerste seconde, het volume, de fragmentduur en de beeldvoorkeur: automatisch, MP4-video of gekoppelde afbeelding/GIF.
- Een fragment mag maximaal **120 seconden** duren.
- Echte afspeelbeurten en lokale browserpreviews worden afzonderlijk vastgelegd in de auditlog. De softwarelog bevat fouten met volledige traceback.

## Belangrijk over de veiligheid

Je browser gaf eerder een melding 'Virus gedetecteerd' bij een vorige ZIP-download. **Schakel Microsoft Defender niet uit, maak geen uitzonderingen en herstel geen bestand uit quarantaine zonder onderzoek.** Kijk bij Windows-beveiliging, Virus- en bedreigingsbeveiliging, Beveiligingsgeschiedenis wanneer een download opnieuw verdwijnt. Het feit dat dit project broncode bevat, bewijst op zichzelf niet dat iedere download veilig is.

Het extra pakket `imageio-ffmpeg` levert een eigen FFmpeg-programma mee. Daardoor is de installatie groter dan bij MP3 alleen. Installeer alleen vanuit de aangegeven Python-afhankelijkheden en niet vanaf willekeurige downloadsites.

## Stap 1. Sluit het huidige DrostSoundboard

Sluit de webpagina en vooral het bijbehorende terminalvenster. Tijdens het vervangen mogen er geen Python-audiostreams meer actief zijn.

## Stap 2. Maak een back-up van je broncode en bibliotheek

Open PowerShell en voer het volgende uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.py,.\DrostSoundboard\*.bat,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_fase4.zip -Force

Copy-Item "$env:LOCALAPPDATA\DrostSoundboard\bibliotheek.sqlite3" ".\DrostSoundboard_bibliotheek_backup.sqlite3" -ErrorAction SilentlyContinue
```

De bibliotheek staat in `%LOCALAPPDATA%\DrostSoundboard\bibliotheek.sqlite3`. De originele mediabestanden staan in `%LOCALAPPDATA%\DrostSoundboard\media` en worden niet overschreven door deze update.

## Stap 3. Pak de update uit

Sla `DrostSoundboard_Fase4_Update.zip` op in je Downloads-map en voer uit:

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase4_Update.zip" -DestinationPath . -Force
cd .\DrostSoundboard
```

Het ZIP-bestand bevat bovenaan de map `DrostSoundboard` en de update vervangt alleen broncode en documentatie. Je bestaande `.venv` en AppData blijven staan.

## Stap 4. Installeer de twee nieuwe onderdelen

```powershell
.\Installeer_ontwikkelomgeving.bat
```

Nu worden `imageio-ffmpeg` (MP4) en `Pillow` (statische GIF-miniatuur) toegevoegd aan de bestaande Python-omgeving. Op Windows hoef je FFmpeg niet los te installeren.

Controleer:

```powershell
.\.venv\Scripts\python.exe -c "import sounddevice, soundfile, soxr, imageio_ffmpeg, PIL; print('Geluid en video klaar')"
```

## Stap 5. Test de software

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

De tests gebruiken nepapparaten voor Windows-audio, een lokaal HTTP-serverproces en zelf gegenereerde audio/video. Ze bewijzen niet dat de audio op iedere pc zonder storingen werkt. Als er een foutmelding komt: stuur de volledige traceback, geen screenshot van alleen het laatste regeltje.

## Stap 6. Start DrostSoundboard

```powershell
.\Start_DrostSoundboard.bat
```

De webpagina opent op `http://127.0.0.1:8765/`, of een vrije andere poort als deze bezet is. **Laat het PowerShell-venster open**, want Python doet nog steeds het audiowerk.

## Stap 7. Test Preview zonder Discord

1. Klik **Geluiden toevoegen** en kies eerst een korte MP3.
2. Klik het knopje **Preview** op die kaart. Je hoort dit via de standaard Windows-uitvoer van je browser, normaal je Razer.
3. Klik **Preview stoppen**. Het geluid en de animatie moeten stoppen.
4. Controleer dat de meter van `CABLE Output` niet beweegt vanwege de preview. Praat eventueel niet tijdens deze proef.
5. Open `Open_Logboeken.bat`. In `audit.jsonl` staan `preview_gestart` en `preview_gestopt` met de duur en reden.

De browser kan automatisch afspelen blokkeren. Klik de Preview-knop nog een keer als het afspelen door de browser werd geweigerd. Dat is geen reden om browserbeveiliging uit te schakelen.

## Stap 8. Test echt afspelen via Razer en VB-CABLE

1. Kies de **Razer USB Sound Card** als microfoon.
2. Kies bij **Luister via** de Razer-hoofdtelefoon of de automatische optie.
3. Zet **Zelf meeluisteren** aan.
4. Klik **Verbinden** en zet **Soundboard actief** aan.
5. Klik op een gevulde favoriete geluidskaart, dus niet op de Preview-knop.
6. Je moet nu het effect zelf horen. Op Windows moet `CABLE Output` het effect ontvangen. Je eigen stem mag niet als een vertraagde echo terugklinken.
7. Klik **Stop geluid**. Het effect stopt, maar je stem blijft via VB-CABLE lopen.

Bij **Gebruikersinstellingen > Spraak en video** kies je in Discord `CABLE Output` als invoerapparaat en je Razer als uitvoer. Zet voor de eerste muziekproef Discord-ruisonderdrukking tijdelijk uit. Controleer het resultaat bij een echte gesprekspartner. Windows mag je Razer als standaardmicrofoon blijven gebruiken.

**Als 'Zelf meeluisteren' geen geluid geeft maar VB-CABLE wel:** kies expliciet de Razer bij **Luister via** en bekijk `%LOCALAPPDATA%\DrostSoundboard\logboeken\software.jsonl`. De aparte headsetdriver kan een andere fout hebben dan de virtuele kabel. De gesprekspartners blijven in dat geval het effect ontvangen.

## Stap 9. Test MP4, afbeelding en GIF

1. Importeer een MP4 met video én audio. Voor een betrouwbare beeldweergave in Chrome of Edge is een gangbaar H.264-videoformaat met AAC-audio aanbevolen. Niet elk MP4-codecprofiel is in iedere browser afspeelbaar.
2. Speel de MP4 af. Alleen Python stuurt de audio naar de kabel. Het beeld speelt zonder geluid in het Now Playing-vlak. Het beeld moet eindigen zodra Python meldt dat de audio is gestopt.
3. Klik in de bibliotheek op de drie puntjes van een MP3. Voeg een foto of GIF toe.
4. Laat **Beeld bij afspelen** op **Automatisch** staan of kies expliciet **Gekoppelde afbeelding of GIF**.
5. Speel het fragment af. De gekoppelde afbeelding is zichtbaar. Een GIF beweegt zolang het fragment actief is en verdwijnt daarna. Het favoriete raster toont alleen de stilstaande miniatuur.
6. Koppel eventueel ook een GIF aan een MP4. Kies dan **Gekoppelde afbeelding of GIF** als je de GIF wilt zien in plaats van het originele videobeeld.

## Logging en storingen

Open de logmap met `Open_Logboeken.bat`:

- `audit.jsonl` beschrijft een afspeelbeurt met de geluidsnaam, unieke ID, start, stop, daadwerkelijk aangeboden audioduur en stopreden. Ook previews en wijzigingen in de meeluisterinstelling worden geregistreerd.
- `software.jsonl` bevat bronbestandsfouten, FFmpeg-fouten, onjuiste parameters, audioapparaatproblemen en volledige Python-tracebacks. Er worden geen ruwe microfoonopnames bewaard.

## Wat deze versie nog niet kan garanderen

- Een browser speelt niet ieder denkbaar MP4-codecprofiel. MP4-audio kan werken terwijl een zeldzaam videocodec niet zichtbaar is.
- De combinatie van Windows-audiokaarten kan op een andere pc andere vertragingen hebben. De headsetmonitor speelt het effect dat de mixer verwerkt, niet je eigen microfoonsignaal.
- De uiteindelijke zelfstandige `.exe`/Windows-installer is nog een aparte projectfase. Voor ontwikkelen heb je nog Python 3.13 nodig.
