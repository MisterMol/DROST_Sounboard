# DrostSoundboard 6.0.0-beta.2: professionele VB-CABLE-controle

Deze gerichte broncodepatch bouwt voort op **6.0.0-beta.1**. De audiomixer, media, hotkeys en opslag veranderen niet. **De officiële eindgebruikersdownload blijft alleen de Windows-installer.** Een portable versie kan desgewenst later worden toegevoegd.

## Wat merkt een gebruiker?

Wanneer het dashboard voor het eerst opent, controleert DrostSoundboard of de gewone VB-CABLE Input **en** VB-CABLE Output via Windows WASAPI zichtbaar en bruikbaar zijn. De controle leest alleen apparaatnamen en kanaalaantallen. Er wordt geen microfoon ingeschakeld en niets afgespeeld.

* **Beide kanten gevonden:** geen melding. De microfoon kan zoals altijd worden verbonden.
* **Geen kanten gevonden:** een rustige melding boven de audio-instellingen, met een knop naar de [officiële VB-Audio-pagina](https://vb-audio.com/Cable/) en een knop **Opnieuw controleren**.
* **Slechts één kant:** een andere tekst legt uit dat de apparaten mogelijk uitgeschakeld zijn.
* **Meerdere bijpassende kanten:** DrostSoundboard weigert een willekeurige keuze en geeft uitleg.
* **Fout bij de controle:** dit wordt niet voor een ontbrekende driver aangezien; de technische oorzaak verschijnt in het softwarelog.

Een melding verschijnt in het dashboard, niet als Windows-melding die elk loginmoment wordt getoond. De bibliotheek en lokale geluidsvoorbeelden blijven werken wanneer VB-CABLE ontbreekt. Voor audio naar Discord of games is VB-CABLE nodig. Bij een bekende ontbrekende/onvolledige kabel begint de app geen poging tot verbinden.

De leverancier laat VB-CABLE als afzonderlijke Windows-driver installeren. Daarvoor kunnen administratorrechten en een herstart nodig zijn. DrostSoundboard vraagt die rechten niet zelf aan en installeert geen driver stilzwijgend. De officiële download is https://vb-audio.com/Cable/.

## Installeren op je ontwikkelcomputer

1. Download `DrostSoundboard_6_0_0_Beta2_VBCable_Update.zip` en `Controleer_En_Installeer_6_0_Beta2.ps1` naar **Downloads**.
2. Bewaar een kopie van je broncode en installeer **niet tijdens een gesprek**. De ontwikkelupdater stopt het huidige DrostSoundboard-proces tijdelijk.
3. Open PowerShell en voer uit:

```powershell
$installatie = Join-Path $env:USERPROFILE 'Downloads\Controleer_En_Installeer_6_0_Beta2.ps1'
Unblock-File -LiteralPath $installatie
& $installatie
```

Het installatiescript controleert eerst of je werkelijk versie `6.0.0-beta.1` gebruikt en of de SHA256 van de ZIP klopt. Vervolgens roept het **de bestaande Updater 1.2** met het expliciete updatebestand aan. Die maakt zelf een back-up, vraagt om `JA`, draait tests en controleert de nieuwe procesversie. `Unblock-File` betekent niet dat beveiligingswaarschuwingen voor willekeurige programma's uitgeschakeld worden.

**Opmerking:** dit werkt de **broncode-installatie** bij. Als je een eerder gebouwde Setup.exe hebt geïnstalleerd, dan verandert die geïnstalleerde EXE niet vanzelf: daarvoor moet je eerst een nieuwe installer bouwen en daarna het reguliere release-updatetraject gebruiken.

## Controleer de nieuwe versie

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects\DrostSoundboard"
.\Update_DrostSoundboard.cmd -AlleenProcescontrole
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Open in het dashboard een tabblad en controleer de status van VB-CABLE. Je kunt ook zonder audiostream een HTTP-status opvragen, zolang DrostSoundboard draait:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/api/vereisten/vb-cable'
```

Dit endpoint werkt alleen wanneer de app op poort 8765 gestart is. Als die bezet is, kiest DrostSoundboard een andere lokale poort. Het dashboard op de gekozen poort blijft dan de beste manier om te testen.

## Bouw een nieuwe, zelfstandige installer

Alleen nodig voor de ontwikkelaar:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects\DrostSoundboard"
.\Bouw_Windows_Release.ps1 -GitHubRepository 'https://github.com/MisterMol/DROST_Sounboard'
Get-ChildItem .\release-velopack\*Setup.exe
```

Het bouwscript gebruikt nu expliciet `--runtime win-x64`. De GitHub-proefworkflow bevat uitsluitend de **Setup.exe** en de technische bestanden die automatische updates mogelijk maken, **niet** de portable ZIP. Bied de Setup.exe als enige download aan eindgebruikers aan. De andere technische assets zijn nodig voor het release-updateproces en hoeven gebruikers niet handmatig te kiezen.

## Broncode naar GitHub synchroniseren

De clone op je Desktop is een **andere map** dan de werkende ontwikkelinstallatie. Na de geslaagde update moet je de veranderde bronbestanden nog naar die clone kopiëren en committen. Dat gebeurt niet automatisch. Zie ook de walkthrough die naast dit ZIP-bestand is meegeleverd.

## Aandachtspunten

* Een gebundelde Setup.exe blijft zonder code signing mogelijk, maar kan SmartScreen-waarschuwingen krijgen.
* De statuscontrole zegt iets over **zichtbare en bruikbare audioapparaten**, niet met zekerheid of er ergens driverbestanden op de schijf staan.
* Een echte microfoon/Discord-test en installatie op een schoon Windows-account zijn nog nodig voordat 6.0 openbaar kan worden aangekondigd als stabiel.
* Update van een geïnstalleerde beta.1 naar beta.2 via GitHub is pas te testen als een officiële beta-release met de bijbehorende updatebestanden gepubliceerd is.
