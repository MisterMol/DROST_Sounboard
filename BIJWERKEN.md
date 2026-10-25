# DrostSoundboard bijwerken tijdens ontwikkeling

Dit is de **ontwikkel-updater 1.2**. Hij werkt vanuit de map waarin `start_desktop.py` staat. Er is nergens een Windows-gebruikersnaam, schijfletter of vaste projectlocatie ingesteld. Voor de latere publieke installer maken we een aparte release-updater.

## Eenmalig

Pak `DrostSoundboard_Updater_1_2_Procesherstel.zip` uit **boven op je bestaande projectmap**. Vervang de oude `Update_DrostSoundboard.ps1` en `.cmd`.

Controleer daarna alleen welke instantie actief is, zonder iets te stoppen:

```powershell
cd "<jouw-projectmap>"
.\Update_DrostSoundboard.cmd -AlleenProcescontrole
```

Het programma herkent zowel de starter van de **eigen virtuele Python-omgeving** als het echte Python-proces vanuit de basisinstallatie. Het controleert ook het precieze startscript en de huidige Windows-sessie. Je andere Python-projecten worden niet gestopt.

## Elke volgende patch

1. Download het officiële update-ZIP-bestand naar de Downloads-map van je Windows-account. Staat het ergens anders? Gebruik `-UpdateBestand` met het volledige pad.
2. **Werk niet bij tijdens een call.** De virtuele microfoon wordt tijdelijk onderbroken.
3. Dubbelklik op `Update_DrostSoundboard.cmd`.
4. Controleer de bestandsnaam en SHA256 van de getoonde update. Bevestig met `JA`.
5. De updater sluit de huidige DrostSoundboard-instantie, bewaart de geraakte bestanden, installeert de patch, draait alle tests en start opnieuw.
6. Een update is pas geslaagd als de server antwoordt met de **verwachte codeversie** én het proces-ID van een echt, nieuw gestart DrostSoundboard-proces. De PID van de venv-starter mag hiervan verschillen.

Dit script accepteert niet zomaar de PID die `Start-Process` teruggeeft. Een startproces kan immers eerder eindigen dan het eigenlijke achtergrondproces.

Bij een mislukte test of ongeldige herstart worden de gewijzigde bestanden teruggezet. Als de app eerder draaide, wordt geprobeerd de oude versie weer te starten. Controleer altijd de uitvoer voordat je weer een gesprek begint.

## Extra commando's

Alleen processen en actieve versie bekijken, zonder wijzigen:

```powershell
.\Update_DrostSoundboard.cmd -AlleenProcescontrole
```

Een specifiek updatebestand kiezen:

```powershell
.\Update_DrostSoundboard.cmd -UpdateBestand "D:\Mijn downloads\DrostSoundboard_5_9_4_Update.zip"
```

Bijwerken zonder automatisch opnieuw te starten:

```powershell
.\Update_DrostSoundboard.cmd -NietOpnieuwStarten
```

Alle updatelogs en reservekopieën staan per Windows-account in `%LOCALAPPDATA%\DrostSoundboard\updates`.

## Veiligheid en beperkingen

* De updater stopt alleen gecontroleerde DrostSoundboard-processen. Hij controleert de uitvoerbare venv- en basis-Pythonbestanden, de exacte opdrachtregel, de Windows-sessie en de processtarttijd. Een oud procesnummer alleen is nooit voldoende.
* Er mag maar één updater tegelijk actief zijn. Een tweede update krijgt een duidelijke fout.
* ZIP-bestanden worden op mapstructuur, beschermde mappen, onveilige paden, links en dubbele bestandsnamen gecontroleerd. Toch is dit **geen beveiligde supply-chain**: een ZIP met deze naam is niet automatisch betrouwbaar. Gebruik alleen bronbestanden die je vertrouwt; automatisch ondertekende GitHub-releases volgen later.
* De huidige ontwikkelapp heeft nog geen veilige stop-API. Daarom beëindigt de updater herkende achtergrondprocessen. Dat onderbreekt audio en is niet geschikt tijdens een gesprek.
* De updater raakt `.venv`, SQLite, audiobestanden en instellingen in `%LOCALAPPDATA%` niet aan. Bij patches die een databasemigratie of nieuwe pip-afhankelijkheden nodig hebben, is een aparte migratie- of installatiestap vereist.
* Windows Defender en SmartScreen mogen niet worden uitgeschakeld voor een update. Controleer een melding voordat je doorgaat.
* De scripts worden niet met administratorrechten uitgevoerd. In een toekomstige gecompileerde Windows-versie neemt een afzonderlijke installer de taak over.

## Regressietests procesbeheer (Updater 1.2)

Voordat je een update installeert kun je de procesherkenning testen met gesimuleerde Windows-processen. Deze tests stoppen **geen** processen:

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\tests\Controleer_Updater_Procesbeheer.ps1
```

De extra uitleg over de herstelpatch staat in `UPDATER_1_2_HERSTEL.md`.
