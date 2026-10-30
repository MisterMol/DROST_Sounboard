# DrostSoundboard op GitHub zetten

Mijn hobbyproject staat bedoeld voor [MisterMol/DROST_Sounboard](https://github.com/MisterMol/DROST_Sounboard). Let op de bestaande repositorynaam: **Sounboard**, dus zonder de tweede `d`.

## Eerst: twee soorten downloads

**Voor vrienden:** plaats de gecontroleerde Windows `Setup.exe` bij een GitHub **Release**. Eén dubbelklik, geen Git of Python nodig.

**Voor mensen die code willen zien:** publiceer de broncode in de repository. Ze kunnen `git clone` uitvoeren, maar krijgen dan **niet automatisch** de volledige binaire stemruntime, modelgewichten of persoonlijke geluiden. Dat is expres zo, en staat ook in de README.

## Broncode bijwerken

1. Maak in je huidige project eerst de documentatiepatch af.
2. Open Git Bash of PowerShell in de projectmap.
3. Controleer welke bestanden Git wil meenemen. Gebruik geen `git add -A` als je niet weet wat er in die map staat.
4. Kijk naar de `.gitignore`: die sluit `.venv`, de stemruntime, modellen, databases, persoonlijke media, builds en logs uit. **De ingebouwde Bob- en Elise-MP3’s zijn expliciet toegestaan en moeten wel mee.**
5. Voer `Controleer_Voor_GitHub.cmd` uit voordat je pusht. Dat script verstuurt niets.

Als de projectmap al een Git-repository is, kun je de **volledige actuele broncode** klaarmaken, dus niet alleen de bestanden uit deze patch:

```powershell
git remote -v
git status --short
# Alle broncode, tests, bouwscripts en actuele documentatie (geen eigen data):
git add .gitignore LICENSE
git add app tests assets hulpmiddelen
# De twee ingebouwde stemvoorbeelden moeten ook in een clone aanwezig zijn:
git add app/audio/stemvoorbeelden/hello_my_name_is_bob.mp3 app/audio/stemvoorbeelden/hello_my_name_is_elise.mp3
git add '*.py' '*.bat' '*.cmd' '*.ps1' '*.md' 'requirements*.txt'
# Als je .github al in de lokale repository hebt:
if (Test-Path .github) { git add .github }
# Controleer voor de commit zorgvuldig wat klaarstaat:
.\CONTROLEER_VOOR_GITHUB.cmd
git diff --cached --stat
git diff --cached --check
git status --short
git commit -m "release: RC4 broncode, handleidingen en installer"
git push origin main
```

De GitHub-controle **stopt** bij een geënsceneerde `.db`, `.exe`, `.dll`, modelgewicht, archief of persoonlijk mediabestand. **Alleen MP3’s direct in `app/audio/stemvoorbeelden/` zijn als ingebouwde voorbeelden toegestaan.** De controle eist ook dat `hello_my_name_is_bob.mp3` en `hello_my_name_is_elise.mp3` werkelijk in de Git-index staan. Als een ander verboden bestand is gestaged, haal het uit de Git-index. Het script kijkt alleen naar wat in deze commit verandert. Kijk ook naar bestaande repositorybestanden en eerdere commits: `.gitignore` wist geen oude uploads uit de Git-geschiedenis.

Controleer na het `git add`-commando dat beide voorbeelden worden meegenomen:

```powershell
git ls-files -- app/audio/stemvoorbeelden/
```

Je hoort de twee MP3-bestanden te zien. Staan ze er niet, dan is de GitHub-clone onvolledig. De patch bevat bewust geen MP3-audio en verwijdert of vervangt je bestaande voorbeelden niet. Controleer de rechten op beide opnames voordat je publiek pusht.

Controleer bij `git remote -v` of je echt de bedoelde repository hebt. Gebruik je een andere branch, pas `main` aan. De push vraagt eventueel om een normale GitHub-aanmelding. Zet nooit tokens of wachtwoorden in broncode of scripts.

Als je huidige map nog **geen** `.git` heeft, clone dan eerst je bestaande repository in een **nieuwe map** en kopieer alleen de gecontroleerde bronbestanden daarheen. Vermijd het kopiëren van `.venv`, `stem-runtime`, `release-velopack`, logs en je geluidsbibliotheek. Gebruik vervolgens de normale `git add`-stappen. Maak geen tweede, losse Git-geschiedenis over de bestaande repository heen.

## De Windows Setup delen via GitHub Releases

1. Bouw op je Windowsontwikkelcomputer met `Bouw_Windows_Release.cmd`.
2. De bouwer draait de volledige testset en controleert daarna de ingebouwde EXE en stemworker. Hij publiceert niets automatisch.
3. Zoek het **Delen**-pakket binnen de nieuwste, geslaagde map onder `release-velopack`. Controleer `BOUWCONTROLE.json` en `SHA256SUMS.txt`.
4. **Test de Setup eerst op een tweede Windowscomputer zonder Python.** Controleer ook VB-CABLE, Preview, Uitzenden, Stop, afsluiten, dashboardindelingen en de stemvervormer.
5. Controleer vóór een publieke download alle licenties en rechten op de meegeleverde modelgewichten, DLL's, FFmpeg en stemvoorbeelden. Zie `THIRD_PARTY_NOTICES.md`.
6. Maak vervolgens op GitHub een release aan, bijvoorbeeld `v6.1.0-rc.4`. Vink **Pre-release** aan. Voeg de geteste Setup toe als asset, eventueel samen met de SHA256-informatie.
7. Zet in de releasetekst dat VB-CABLE voor de virtuele microfoon apart nodig is, met de [officiële link](https://vb-audio.com/Cable/).

**Let op de versie:** de patch wijzigt de app van RC3 naar RC4 omdat er een zichtbare wijziging in de appcode is gedaan. Verspreid een nieuw gebouwde Setup niet met het oude RC3-versienummer. De volgende update wordt voorlopig handmatig gedeeld. Automatische updates via GitHub zijn nog niet geverifieerd.

## Clone of Setup?

```powershell
# Broncode, voor wie wil ontwikkelen:
git clone https://github.com/MisterMol/DROST_Sounboard.git
cd DROST_Sounboard
.\Start_Na_Git_Clone.cmd
```

Voor direct gamen is de download onder **Releases** de bedoelde route. Een clone van de repository is geen volwaardige installer.
