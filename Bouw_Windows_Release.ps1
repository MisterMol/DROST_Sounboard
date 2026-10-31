#requires -Version 5.1
<#
  Bouw een Windows x64 Velopack-release vanuit de huidige broncode.
  Draait alle Python-tests, PyInstaller (onedir), een EXE-smoketest en vpk.
  Publiceert NOOIT vanzelf op GitHub. Daarmee kunnen ontwikkelaars eerst
  op een echte Windows-pc bevestigen dat microfoon en installer werken.
#>
[CmdletBinding()]
param(
    [string] $GitHubRepository = '',
    [switch] $AlleenExe,
    [string] $ResultaatBestand = '',
    [string] $BouwId = '',
    [switch] $Compact
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

if ($env:OS -ne 'Windows_NT') { throw 'RELEASE-001: dit bouwscript werkt alleen op Windows.' }
if ([IntPtr]::Size -ne 8) { throw 'RELEASE-002: gebruik 64-bits PowerShell en Python 3.13 x64.' }
$project = Split-Path -Parent $PSCommandPath
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'RELEASE-003: .venv ontbreekt. Voer eerst Installeer_ontwikkelomgeving.bat uit.'
}
# Controleer de packer vooraf, niet pas na een complete EXE-bouw.
$vpkPad = ''
if (-not $AlleenExe) {
    $vpk = (Get-Command vpk.exe -ErrorAction SilentlyContinue | Select-Object -First 1)
    $vpkPad = if ($vpk) { $vpk.Source } else { Join-Path $env:USERPROFILE '.dotnet\tools\vpk.exe' }
    if (-not (Test-Path -LiteralPath $vpkPad -PathType Leaf)) {
        throw 'RELEASE-014: vpk ontbreekt. Installeer .NET SDK 8 en voer uit: dotnet tool install --global vpk --version 1.2.161'
    }
}
$bronurl = ''
if ($GitHubRepository) {
    if ($GitHubRepository -cnotmatch '^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$') {
        throw 'RELEASE-004: GitHubRepository moet https://github.com/eigenaar/repository zijn.'
    }
    $bronurl = $GitHubRepository.TrimEnd('/')
}
$versieBron = Get-Content -LiteralPath (Join-Path $project 'app\diagnostiek\logboek.py') -Raw -Encoding UTF8
$match = [regex]::Match($versieBron, '(?m)^VERSIE_VAN_DE_APP\s*=\s*["'']([^"'']+)["'']')
if (-not $match.Success) { throw 'RELEASE-005: de centrale versie is niet gevonden.' }
$versie = $match.Groups[1].Value
# Eén vaste versie per release. Lokale herbouw krijgt een eigen uitvoermap,
# niet ongemerkt een ander versienummer of een overschreven publicatie.
if (-not $BouwId) { $BouwId = [guid]::NewGuid().ToString('N') }
if ($BouwId -cnotmatch '^[a-f0-9]{32}$') { throw 'RELEASE-026: ongeldig bouwkenmerk.' }
$werkmap = Join-Path $env:TEMP ('DrostSoundboard_Release_' + $BouwId)
$releasebasis = Join-Path $project 'release-velopack'
if ($ResultaatBestand -and (Test-Path -LiteralPath $ResultaatBestand)) {
    throw 'RELEASE-027: resultaatbestand bestaat al. Begin een nieuwe bouwpoging.'
}
$dist = Join-Path $project 'dist\DrostSoundboard'
New-Item -ItemType Directory -Path $werkmap | Out-Null
Push-Location $project
$bouwslot = $null
try {
    try {
        $bouwslot = [System.IO.File]::Open((Join-Path $project '.drost-release.lock'),
            [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None)
    } catch {
        throw 'RELEASE-029: er loopt al een releasebouw of de projectmap is niet schrijfbaar.'
    }
    $planBestand = Join-Path $werkmap 'bouwplan.json'
    & $python -B -m app.desktop.releasevoorbereiding plan --project $project --versie $versie --bouw-id $BouwId --uitvoer-json $planBestand
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE-006: versie of uitvoermap ongeldig. Geen build gestart.' }
    $bouwplan = Get-Content -LiteralPath $planBestand -Raw -Encoding UTF8 | ConvertFrom-Json
    $release = $bouwplan.uitvoer
    $kanaal = $bouwplan.kanaal
    if (-not $ResultaatBestand) { $ResultaatBestand = Join-Path $release 'BOUWRESULTAAT.json' }
    Write-Host "Versie: $versie. Kanaal: $kanaal. Afzonderlijke bouwmap: $release"
    $config = Join-Path $werkmap 'releasebron.json'
    $configInhoud = @{repository_url=$bronurl; channel=$kanaal; ai_stemmen_meeleveren=(-not $Compact)} | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($config, $configInhoud, [System.Text.UTF8Encoding]::new($false))

    if ($Compact) {
        Write-Host '0/5: compacte basisbuild zonder optionele AI-stemruntime.'
    } else {
        Write-Host '0/5: bestaande stemruntime controleren, zonder modellen te downloaden...'
        & $python -B -c "from app.audio.natuurlijke_stem.runtimecontrole import valideer_runtime; valideer_runtime('stem-runtime')"
        if ($LASTEXITCODE -ne 0) { throw 'RELEASE-022: de bestaande stemruntime is onvolledig of gewijzigd.' }
    }
    Write-Host '1/5: afhankelijkheden voor releasebouwer installeren...'
    & $python -m pip install -r requirements.txt -r requirements-release.txt -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE-007: afhankelijkheden installeren is mislukt.' }
    # De basisstemfilters hebben nog wel de kleine, afzonderlijke native motor nodig.
    # De grote AI-modelruntime is optioneel; deze DLL is dat niet.
    $dspMotor = Join-Path $project 'app\audio\native\win-x64\drost_stem.dll'
    if (-not (Test-Path -LiteralPath $dspMotor -PathType Leaf)) {
        throw 'RELEASE-030: drost_stem.dll ontbreekt. Deze DLL is ook in RC6 Compact nodig voor gewone stemfilters.'
    }
    Write-Host 'Release-icoon en splash controleren of vanuit het bestaande logo aanmaken...'
    & $python -B -m hulpmiddelen.bereid_releaseassets_voor
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE-031: Windows-releaseafbeeldingen ontbreken of verschillen van het logo.' }
    Write-Host '2/5: volledige automatische tests draaien...'
    & $python -m unittest discover -s tests -q
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE-008: tests faalden; geen build gemaakt.' }

    Write-Host '3/5: zelfstandige vensterloze PyInstaller-app maken...'
    $optioneleModeldata = @()
    if (-not $Compact) { $optioneleModeldata = @('--add-data', 'stem-runtime:stem-runtime') }
    & $python -m PyInstaller `
        --onedir --windowed --noupx --clean --noconfirm `
        --name DrostSoundboard `
        --icon (Join-Path $project 'assets\release\DrostSoundboard.ico') `
        --paths . `
        --add-data 'app/webinterface/statisch:app/webinterface/statisch' `
        --add-data 'app/audio/stemvoorbeelden:app/audio/stemvoorbeelden' `
        --add-binary 'app/audio/native/win-x64/drost_stem.dll:app/audio/native/win-x64' `
        --add-data 'app/audio/native/stembouw.json:app/audio/native' `
        --add-data 'app/audio/native/LICENTIES.txt:app/audio/native' `
        @optioneleModeldata `
        --add-data "${config}:app/desktop" `
        --collect-all imageio_ffmpeg `
        --collect-all sounddevice `
        --collect-all _sounddevice_data `
        --collect-all soundfile `
        --collect-all _soundfile_data `
        --collect-all soxr `
        --collect-all pystray `
        --collect-all velopack `
        --hidden-import pystray._win32 `
        start_desktop.py
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE-009: PyInstaller kon de EXE niet maken.' }
    $exe = Join-Path $dist 'DrostSoundboard.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'RELEASE-010: de EXE ontbreekt.' }

    Write-Host '4/5: een echte EXE-smoketest uitvoeren, zonder audio te starten...'
    $diagnose = Join-Path $werkmap 'resultaat.json'
    $proces = Start-Process -FilePath $exe `
        -ArgumentList ('--controleer-release "' + $diagnose + '"') `
        -WorkingDirectory $project -PassThru
    if (-not $proces.WaitForExit(90000)) {
        Stop-Process -Id $proces.Id -Force -ErrorAction SilentlyContinue
        throw 'RELEASE-011: de EXE-smoketest duurde langer dan 90 seconden; de bouw stopt.'
    }
    $proces.Refresh()
    if ($proces.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $diagnose)) {
        throw 'RELEASE-012: de gebundelde EXE kon de eigen bestanden niet controleren.'
    }
    $status = Get-Content -LiteralPath $diagnose -Raw | ConvertFrom-Json
    if ($status.versie -ne $versie) { throw 'RELEASE-023: de gecontroleerde EXE heeft niet de verwachte versie.' }
    if (-not $status.geslaagd) { throw ('RELEASE-017: smoketest faalde: ' + (Get-Content -LiteralPath $diagnose -Raw)) }
    if ($bronurl -and -not $status.repository_geverifieerd) {
        throw 'RELEASE-013: de ingevoegde GitHub-repository is niet in de EXE aanwezig.'
    }
    Write-Host 'EXE-smoketest geslaagd.' -ForegroundColor Green
    # De standaardbouw controleert de volledige worker; compact rapporteert afwezigheid expliciet.
    # Controleer ook de afzonderlijke stemmotor in de UITGEBRACHTE map.
    $stemmap = Join-Path $dist '_internal\stem-runtime'
    $stemexe = Join-Path $stemmap 'DrostStemWorker.exe'
    $stemmodel = Join-Path $stemmap 'G_500000.pth'
    $stemrapport = Join-Path $werkmap 'stemtest.json'
    if ($Compact) {
        if (Test-Path -LiteralPath $stemmap) { throw 'RELEASE-029: AI-stemruntime toch in compacte build.' }
        $stemstatus = @{ passed = $false; finite = $false; reset_ok = $false;
            optioneel_niet_meegeleverd = $true } 
        [System.IO.File]::WriteAllText($stemrapport, ($stemstatus | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
    } else {
    if (-not (Test-Path -LiteralPath $stemexe -PathType Leaf)) { throw 'RELEASE-018: de gebundelde stemmotor ontbreekt.' }
    $stemproces = Start-Process -FilePath $stemexe -ArgumentList ('--model "' + $stemmodel + '" --selftest "' + $stemrapport + '"') -WorkingDirectory $stemmap -PassThru -WindowStyle Hidden
    if (-not $stemproces.WaitForExit(120000)) {
        Stop-Process -Id $stemproces.Id -Force -ErrorAction SilentlyContinue
        throw 'RELEASE-019: de proefstemtest reageert niet. Geen installer gemaakt.'
    }
    $stemproces.Refresh()
    if ($stemproces.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $stemrapport)) { throw 'RELEASE-020: de gebundelde stemtest mislukte.' }
    $stemstatus = Get-Content -LiteralPath $stemrapport -Raw | ConvertFrom-Json
    if (-not $stemstatus.passed) { throw 'RELEASE-021: de gebundelde proefstem haalt de verwerkingscontrole niet.' }
    Write-Host 'Gebundelde stemmotor gecontroleerd. Dit is geen luistertest.' -ForegroundColor Green
    }
    if ($AlleenExe) {
        Write-Host "Losse EXE-testbuild: $exe" -ForegroundColor Green
        Write-Warning 'Dit is nog GEEN automatische-updateinstallatie. Deel de map dist niet als publieke release.'
        return
    }

    Write-Host '5/5: Velopack Setup.exe en updatepakketten bouwen...'
    # Deze uitvoermap is door deze poging aangemaakt. Geen oude feed hergebruiken.
    $setupPad = Join-Path $release $bouwplan.installer_naam
    if (@(Get-ChildItem -LiteralPath $release -Force).Count -ne 0) {
        throw 'RELEASE-028: de nieuwe bouwmap is niet leeg. Geen bestaande release overschreven.'
    }
    $packStart = [DateTime]::UtcNow
    & $vpkPad pack `
        --runtime win-x64 `
        --packId 'DrostSoundboard.Desktop' `
        --packVersion $versie `
        --packTitle 'DrostSoundboard' `
        --icon (Join-Path $project 'assets\release\DrostSoundboard.ico') `
        --splashImage (Join-Path $project 'assets\release\DrostSoundboard_Installatie.png') `
        --channel $kanaal `
        --packDir $dist `
        --mainExe 'DrostSoundboard.exe' `
        --outputDir $release
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE-015: Velopack kon de installer niet maken.' }
    if (-not (Test-Path -LiteralPath $setupPad -PathType Leaf)) { throw 'RELEASE-016: de nieuwe Velopack Setup.exe ontbreekt.' }
    $nieuweSetup = Get-Item -LiteralPath $setupPad
    if ($nieuweSetup.LastWriteTimeUtc -lt $packStart.AddSeconds(-2)) {
        throw 'RELEASE-024: de installer hoort niet aantoonbaar bij deze bouwpoging.'
    }

    $lijst = Join-Path $release 'SHA256SUMS.txt'
    $regels = @(Get-ChildItem -LiteralPath $release -File |
        Where-Object { $_.Name -ne 'SHA256SUMS.txt' } |
        ForEach-Object { $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); "$hash  $($_.Name)" })
    [System.IO.File]::WriteAllLines($lijst, $regels, [System.Text.UTF8Encoding]::new($false))
    & $python -B -m app.desktop.releasevoorbereiding afronden --project $project --plan $planBestand --exe-rapport $diagnose --stem-rapport $stemrapport --resultaat $ResultaatBestand
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE-025: geen gecontroleerde deelmap en geen geslaagd bouwresultaat.' }
    Write-Host "Bouwresultaat: $ResultaatBestand"
    Write-Host "Setup en releasepakketten: $release" -ForegroundColor Green
    if (-not $bronurl) { Write-Warning 'Handmatige updates: er is geen automatische updatebron geconfigureerd.' }
    Write-Warning 'Een geslaagde bouw is geen productiegoedkeuring. Test op Windows zonder ontwikkelomgeving, inclusief audio, bijwerken en verwijderen.'
    Write-Warning 'Code signing ontbreekt; SmartScreen kan waarschuwen. VB-CABLE moet apart worden geïnstalleerd.'
}
finally {
    if ($null -ne $bouwslot) { $bouwslot.Dispose() }
    Pop-Location
    if (Test-Path -LiteralPath $werkmap) {
        Remove-Item -LiteralPath $werkmap -Force -Recurse -ErrorAction SilentlyContinue
    }
}
