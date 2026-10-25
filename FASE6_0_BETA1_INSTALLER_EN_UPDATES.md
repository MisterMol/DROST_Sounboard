# DrostSoundboard 6.0.0-beta.1: distributiepatch en Windows-walkthrough

**Status:** technisch getest op broncode en Linux-testomgeving; nog **geen** gevalideerde Windows-installer. Dit is een eerste releasepatch, niet de definitieve 6.0.0.

## Belangrijk: welke bronversie?

Deze patch is gebouwd op de volledige **5.9.4-video-en-onderhoud**-projectkopie met **Updater 1.2**. De 6.0-patch uit het oude gesprek was niet beschikbaar. Installeer hem NIET blind over een andere 6.0.0-beta of een aangepaste `start_desktop.py`. De meegeleverde installatiestarter controleert bronversie, bestanden en patchhash voordat hij iets wijzigt.

## Wat is nieuw?

1. `start_desktop.py --achtergrond` start zonder browser en opent ook bij een bestaande desktopinstantie geen extra tabblad.
2. Het systeemvak krijgt `Start met Windows`, `Op updates controleren` en zichtbare updatestatus. De aanmeldstart is standaard uit en gebruikt uitsluitend de blijvende Velopack-starter onder HKCU. Bij verwijderen wordt de eigen registerwaarde opgeruimd.
3. De Velopack Python SDK wordt **alleen in een verpakte Windows-EXE** gebruikt. De ontwikkelinstallatie hoeft Velopack niet te installeren. Automatisch toepassen op iedere dubbelklik staat uit.
4. Als de app daadwerkelijk via Velopack is geïnstalleerd en de officiële publieke GitHub-repository tijdens de bouw is ingesteld, controleert een achtergrondthread ongeveer elke 12 uur op updates. Na een update worden alleen pakketten gedownload; de audio wordt niet gestopt.
5. Bij een normale afsluiting via het systeemvak wordt een al gedownload pakket pas na het afsluiten van audio, sneltoetsen en server ingepland voor installatie. Als de app onverwacht werd afgesloten, gebeurt dit bij de volgende veilige start, vóór er een nieuwe stream bestaat.
6. `Bouw_Windows_Release.ps1` test de broncode, maakt een vensterloze PyInstaller-map, controleert de EXE zonder microfoon, laat Velopack een setup en updatepakketten maken en berekent SHA256. `windows-release-proef.yml` doet dit op Windows in GitHub Actions, nog zonder automatisch te publiceren.

**Opslag:** Velopack gebruikt een afzonderlijke applicatiemap onder `%LOCALAPPDATA%\DrostSoundboard.Desktop`. De bestaande gebruikersgegevens blijven onder `%LOCALAPPDATA%\DrostSoundboard`. Dit is essentieel: bij verwijderen van de applicatie mag de soundbibliotheek niet verdwijnen.

## A. Broncodepatch aanbrengen op de Windows-ontwikkelinstallatie

1. Download `DrostSoundboard_6_0_Beta1_Distributiepatch.zip` en `Controleer_En_Installeer_6_0_Beta1.ps1` naar Downloads.
2. Controleer eerst dat DrostSoundboard op de huidige machine normaal draait (5.9.4) en dat de ontwikkelupdater 1.2 werkt. Laat de installer automatisch stoppen. Voer dit **niet** uit tijdens een gesprek.
3. Open PowerShell en voer uit:

```powershell
$installatiescript = Join-Path $env:USERPROFILE 'Downloads\Controleer_En_Installeer_6_0_Beta1.ps1'
Get-Content -LiteralPath $installatiescript | Select-Object -First 30
Unblock-File -LiteralPath $installatiescript
& $installatiescript
```

4. De starter weigert een andere versie dan `5.9.4-video-en-onderhoud` of een aangepast bronbestand. Dat is bewust. Stuur in dat geval een actuele project-ZIP; gebruik `Expand-Archive -Force` niet als alternatieve upgrade.
5. Als de controles kloppen, vraagt de bestaande updater om `JA`. De updater maakt een back-up, installeert de gewijzigde bestanden, draait tests en herstart de desktopapp. Verwacht `/api/versie` = `6.0.0-beta.1`.

## B. De ontwikkelapp controleren

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects\DrostSoundboard"
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\Start_DrostSoundboard_Desktop.bat
.\Update_DrostSoundboard.cmd -AlleenProcescontrole
```

Sluit het browservenster: de app moet nog in het systeemvak draaien. Controleer de nieuwe systeemvakitems. In de ontwikkelinstallatie zijn `Start met Windows` en binaire updates uitgeschakeld, omdat er nog geen geïnstalleerde Velopack-app is.

## C. De eerste Windows-installatie bouwen

**Alleen voor ontwikkelaars.** Nodig: Python 3.13 x64 met de bestaande `.venv`, .NET SDK 8 en Velopack CLI. Voor de normale eindgebruiker zijn Python en .NET niet nodig.

Installatie van .NET (één keer op de bouwmachine):

```powershell
winget install --id Microsoft.DotNet.SDK.8 --exact
```

Start daarna een NIEUW PowerShell-venster:

```powershell
dotnet --version
dotnet tool install --global vpk --version 1.2.161
```

De releasebouwer installeert PyInstaller 6.22.3 en de Velopack Python SDK 1.2.161 alleen in `.venv`:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects\DrostSoundboard"
.\Bouw_Windows_Release.ps1 -GitHubRepository 'https://github.com/JOUW_NAAM/JOUW_REPO'
```

Vervang de voorbeeld-repository door de echte openbare GitHub-repository. Zonder repository kun je alleen een lokale installatieproef bouwen:

```powershell
.\Bouw_Windows_Release.ps1
```

De output is de map `release-velopack`. Daar staan de Velopack-Setup.exe, het volledige `.nupkg`-updatepakket, `releases.beta.json`, `assets.beta.json` en `SHA256SUMS.txt`. De precieze bestandsnamen worden door Velopack bepaald.

**Let op:** Inno Setup hoef je voor deze distributieroute NIET te installeren. Gebruik de oude `Bouw_Windows_Installer.ps1` niet om dezelfde release te verspreiden. Bestaande gebruikers updaten uitsluitend via Velopack.

## D. Installatie op een schone Windows-computer

1. Test bij voorkeur op een aparte Windows 11 x64-machine of VM met een schoon gebruikersprofiel. DrostSoundboard en Python mogen vooraf niet geïnstalleerd zijn.
2. Start `*Setup.exe` uit `release-velopack`, of later de officiële GitHub-release.
3. Controleer dat de normale snelkoppeling de app en het dashboard opent, zonder terminalvenster.
4. Sluit de browser en open het dashboard opnieuw via het systeemvak.
5. Controleer dat twee keer starten niet twee mixers opent.
6. Zet `Start met Windows` aan. Meld je af en weer aan. Er mag geen browser openen, alleen de trayapp.
7. Test een Windows-gebruikersaccount zonder VB-CABLE. De app mag niet crashen en mag de driver nooit stil installeren.
8. Installeer VB-CABLE apart met de juiste rechten. Test vervolgens microfoon, geluidseffecten, hotkeys, audio tijdens gamen en een actieve Discord-call.
9. Verwijder de app via Windows Geïnstalleerde apps. Controleer dat `%LOCALAPPDATA%\DrostSoundboard\media` en je bibliotheek behouden blijven.

## E. Updatekanaal activeren via GitHub Releases

Deze stap is pas verantwoord nadat **D** is geslaagd.

De releasebouwer maakt een `beta`-kanaal. Velopack heeft zowel de `.nupkg`-pakketten als de release-index nodig. Upload daarom geen losse Setup.exe zonder de bijbehorende updatebestanden.

Voor een publieke repository kun je `vpk upload github` gebruiken. Je moet daarvoor een GitHub-authenticatietoken met uitsluitend de benodigde repo-rechten hebben. Met de GitHub CLI kun je het token tijdelijk aan `vpk` beschikbaar stellen. Publiceer je bèta als **prerelease**:

```powershell
winget install --id GitHub.cli --exact
gh auth login
$repo = 'https://github.com/JOUW_NAAM/JOUW_REPO'
$env:VPK_TOKEN = (gh auth token)
try {
    vpk upload github --repoUrl $repo --outputDir '.\release-velopack' --channel beta --pre --publish --tag v6.0.0-beta.1 --releaseName 'DrostSoundboard 6.0.0 beta 1'
} finally {
    Remove-Item Env:\VPK_TOKEN -ErrorAction SilentlyContinue
}
```

Controleer het resultaat op de GitHub Releases-pagina. De geïnstalleerde app controleert de **tijdens de build ingestelde repository**, niet willekeurige bestanden in Downloads. In een toekomstige 6.0.0-beta.2-release moet het **zelfde `packId` (`DrostSoundboard.Desktop`) en kanaal (`beta`)** behouden blijven. Bouw beta.2 met de nieuwe versie en publiceer de volledige updatebestanden. Test daarna op een eerder met beta.1 geïnstalleerde pc of de update zonder handmatig kopiëren wordt gedownload, en bij een veilige afsluiting wordt toegepast.

De GitHub Actions-workflow `Windows 6.0 releaseproef` maakt de Windows-bouw als artifact. Publiceren is opzettelijk een aparte handeling totdat de volledige end-to-end-test slaagt.

## F. Grenzen van deze eerste patch

- Geen EXE of Setup.exe in deze patch: een echte Windows-build kan niet in de Linux-omgeving worden gevalideerd.
- Geen garantie voor iedere Windows-configuratie. Eerste doel is Windows 11 x64; daarna Windows 10 x64 apart testen.
- Volledig automatische updates vereisen dat de installer met een werkelijke GitHub-repository is gebouwd **en** dat releasepakketten correct zijn gepubliceerd. De eerste beta heeft bovendien nog geen volgende release om naar bij te werken.
- Downloaden is asynchroon. Wanneer de download nog bezig is bij afsluiten, wordt toepassen uitgesteld tot de volgende veilige start.
- VB-CABLE is een afzonderlijke, bewust te installeren driver. Geen automatische driverinstallatie.
- Voor publieke verspreiding eerst FFmpeg- en andere licenties, antivirusgedrag, installerfouten, updateherstel en ongetekende Windows SmartScreen-waarschuwingen beoordelen.
- Gebruik geen update van de ontwikkelmap via Velopack. `Update_DrostSoundboard.cmd` is alleen voor de ontwikkelaar; eindgebruikers hoeven die nooit te gebruiken.

## G. Wat doe je als de patch wordt geweigerd?

Als jouw project **al** `6.0.0-beta1`, `6.0.0-beta.1` of een andere versie noemt, is dat niet dezelfde codebasis als de beschikbare 5.9.4. De installer weigert dan terecht. Maak een nieuwe ZIP van jouw volledige actuele projectmap en laat de wijzigingen gericht mergen. Een oude projectkopie over de nieuwe heen kopiëren kan features vernietigen.
