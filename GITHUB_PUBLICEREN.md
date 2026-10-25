# DrostSoundboard publiceren op GitHub

Repository: https://github.com/MisterMol/DROST_Sounboard

De repositorynaam bevat bewust **Sounboard** (zonder extra `d`). Gebruik daarom precies die URL.

## Advies voor de eerste keer

Werk gewoon in je bestaande ontwikkelmap. Maak apart een schone clone voor GitHub, zodat `.venv`, oude ZIP-pakketten en logboeken niet per ongeluk worden geüpload.

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"
git clone https://github.com/MisterMol/DROST_Sounboard.git DROST_Sounboard_publiceren

$bron = Join-Path (Get-Location) "DrostSoundboard"
$doel = Join-Path (Get-Location) "DROST_Sounboard_publiceren"

# Kopieer broncode en tests, zonder lokale media, caches en virtuele omgeving.
robocopy "$bron\app" "$doel\app" /E /XD __pycache__ /XF *.pyc
robocopy "$bron\tests" "$doel\tests" /E /XD __pycache__ /XF *.pyc
robocopy "$bron\voorbeelden" "$doel\voorbeelden" /E /XF *.mp3 *.mp4
Copy-Item "$bron\start_desktop.py", "$bron\start_webdashboard.py", "$bron\requirements.txt", "$bron\README.md", "$bron\LICENSE", "$bron\SECURITY.md", "$bron\THIRD_PARTY_NOTICES.md", "$bron\CONTRIBUTING.md", "$bron\ARCHITECTUUR.md", "$bron\FASE5_9_DESKTOP_EN_GITHUB.md", "$bron\Start_DrostSoundboard.bat", "$bron\Start_DrostSoundboard_Desktop.bat", "$bron\Start_DrostSoundboard_Ontwikkeling.bat", "$bron\Installeer_ontwikkelomgeving.bat" "$doel"
Copy-Item "$bron\.gitignore" "$doel\.gitignore" -Force
New-Item -ItemType Directory -Path "$doel\.github\workflows" -Force | Out-Null
Copy-Item "$bron\.github\workflows\tests.yml" "$doel\.github\workflows\tests.yml" -Force
```

Let op: `robocopy` geeft ook bij geslaagde kopieën vaak een niet-nulcode. Dat is op zichzelf geen fout.

Controleer vervolgens goed wat Git wil toevoegen:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects\DROST_Sounboard_publiceren"
git status --short
```

Controleer dat er **geen** `.venv`, persoonlijke geluidsbestanden, wachtwoorden, tokens, auditlogs of SQLite-databases tussen staan.

```powershell
git add app tests voorbeelden .github *.py *.bat requirements.txt README.md LICENSE SECURITY.md THIRD_PARTY_NOTICES.md CONTRIBUTING.md ARCHITECTUUR.md FASE5_9_DESKTOP_EN_GITHUB.md .gitignore
git diff --cached --stat
git diff --cached --check
git commit -m "fix: vloeiend mp4-beeld en centrale foutafhandeling"
git push origin main
```

Als de repo om authenticatie vraagt, meld je aan via Git Credential Manager. Zet nooit een GitHub-token letterlijk in code of in een chat.

## Releasebeleid

Publiceer voorlopig de **broncode als bèta**, niet als een kant-en-klare Windows-installer. Versie 6.0 krijgt een PyInstaller-build met Inno Setup; de licenties en ondertekening worden dan apart gecontroleerd.
