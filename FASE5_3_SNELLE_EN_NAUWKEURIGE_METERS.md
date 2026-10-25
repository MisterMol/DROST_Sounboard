# DrostSoundboard 5.3: snelle en nauwkeurige geluidsmeters

## Wat is veranderd?

Deze update past **uitsluitend de niveaumeting, de lokale transportlaag en de visuele meters** aan. De bestaande audiomixer, de VB-CABLE-instellingen, de geluidsbibliotheek, groepen, MP3/MP4-decoders en je 15 favorieten blijven behouden.

- Python meet RMS en samplepiek van ieder audiocallbackblok. Er wordt geen tweede blok meer overgeslagen.
- RMS wordt gewogen over de werkelijk ontvangen frames in de laatste 50 milliseconden. Een halve seconde middelen zou spraak te traag weergeven.
- De samplepiek is een andere grootheid dan RMS en wordt over de laatste 120 milliseconden gemeten. Het witte streepje staat bewust bij RMS, de gemeten samplepiek blijft apart als getal beschikbaar.
- De browser krijgt ongeveer 30 keer per seconde meetgegevens via een lokale EventSource-verbinding op `/api/niveaus/live`. Dat gebruikt één open verbinding in plaats van veel losse HTTP-verzoeken.
- Alleen de zichtbare meter beweegt met een korte stijg- en daaltijd. De dBFS-waarde is niet kunstmatig gladgestreken, maar wordt rechtstreeks uit de echte RMS berekend.
- Bij uitval van de snelle niveaustroom blijft de oude statusroute als terugval bestaan. Als audiocallbacks langer dan 200 milliseconden uitblijven, worden verouderde niveaus niet als actueel aangeboden.
- De server logt bij verbinden de door de driver *gerapporteerde* ingangs- en uitgangslatentie in `software.jsonl` onder `audiostream_latentie_gemeld`.

## Wat betekent die decibelwaarde precies?

De meter geeft **dBFS ten opzichte van genormaliseerde digitale samples** weer, geen dB SPL in de ruimte en geen geluidssterkte van de persoon aan de andere kant van Discord. Voor ons project geldt `dBFS = 20 × log10(RMS)`.

Een digitaal signaal met RMS `0,1` hoort op `−20,0 dBFS` te staan. Een volle sinus met samples tussen min één en plus één heeft ongeveer `−3,01 dBFS` RMS en `0 dBFS` samplepiek. De Razer-microfoon wordt in de huidige mixer met factor `0,8` doorgestuurd, waardoor de kabelmeter bij verder identieke omstandigheden circa `1,94 dB` lager aangeeft dan de microfoonmeter. De mix van geluidseffecten kan die waarde verhogen.

De piek is de hoogste *samplewaarde*, niet een true-peakmeting met oversampling. De audiometer meet wat Python verwerkt of aanbiedt aan VB-CABLE. Zonder de onafhankelijke `Meet_CABLE_Output.bat`-test bevestigt dit niet wat de kabel feitelijk ontvangt.

## Vertraging is niet hetzelfde als meetnauwkeurigheid

De meetwaarde is numeriek herleidbaar tot de audio in Python. Toch is de zichtbare reactie niet letterlijk nul milliseconden: het audioblok moet eerst worden aangeleverd, RMS wordt over maximaal 50 ms berekend, een meetbericht verschijnt ongeveer iedere 33 ms en de browser animeert het resultaat.

PortAudio staat in de bestaande mixer nog op `latency="high"`, omdat we bij de Razer en VB-CABLE eerder driverfouten zagen. Dat profiel vervangen we niet ongemerkt. Kijk in `software.jsonl` naar de nieuw gelogde driverlatentie. Pas als de werkelijke waarden bekend zijn, kunnen we samen gericht een veilig lager profiel testen. Een lager profiel kan meer bufferproblemen geven.

## Installeren op jouw Windows-computer

Sluit DrostSoundboard volledig en open PowerShell:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests -DestinationPath .\DrostSoundboard_backup_voor_meters53.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase5_3_Meters_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard

.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Verwacht in deze codeversie `Ran 197 tests` gevolgd door `OK`. Daarna starten:

```powershell
.\Start_DrostSoundboard.bat
```

Ververs de pagina met `Ctrl + Shift + R` en verbind je Razer-microfoon. Je hoeft geen Python-pakketten bij te installeren.

## Controleer nu dit

1. Spreek een korte lettergreep uit. De meter moet merkbaar eerder reageren dan in 5.2. De bovenste decibelwaarde verandert zodra de server een nieuw werkelijk meetresultaat ontvangt.
2. Stop met praten. De gekleurde balk valt binnen enkele honderden milliseconden terug. De numerieke RMS volgt de gemeten stilte, ook als die onder de zichtbare schaal van −60 dBFS ligt.
3. Speel een bekend WAV-fragment. Kijk of zowel microfoon als VB-CABLE-meter veranderen. De VB-CABLE-meter volgt de mix; je eigen microfoon kan tegelijk stiller blijven.
4. Controleer `Bufferproblemen: 0`. Als dit oploopt, moet de betrouwbaarheid vóór een nog snellere instelling gaan.
5. Open met `Open_Logboeken.bat` de map `software.jsonl` en zoek naar `audiostream_latentie_gemeld`. Deel eventueel de gemelde waarden, **zonder andere persoonlijke loggegevens**.

Als het oude JavaScript lijkt te worden gebruikt, doe eerst een harde herlading in de browser. Als Windows-beveiliging het updatebestand blokkeert, schakel de beveiliging niet uit: controleer eerst de detectie.

## Testresultaten van deze versie

De Python-unit- en HTTP-tests zijn uitgevoerd zonder Windows-hardware: 197 tests geslaagd. Ook de JavaScript-syntax en de meterweergave in Chromium zijn gecontroleerd met nagebootste live niveaus. De echte eind-tot-eind vertraging op jouw Razer en VB-CABLE is nog niet gemeten.
