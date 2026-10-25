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
    [switch] $AlleenExe
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') { throw 'RELEASE-001: dit bouwscript werkt alleen op Windows.' }
if ([IntPtr]::Size -ne 8) { throw 'RELEASE-002: gebruik 64-bits PowerShell en Python 3.13 x64.' }
$project = Split-Path -Parent $PSCommandPath
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'RELEASE-003: .venv ontbreekt. Voer eerst Installeer_ontwikkelomgeving.bat uit.'
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
if ($versie -notmatch '^6\.0\.0-beta\.[0-9]+$') {
    throw "RELEASE-006: voor deze eerste bouwproef wordt een 6.0.0-beta.n versie verwacht, gevonden: $versie"
}
$werkmap = Join-Path $env:TEMP ('DrostSoundboard_Release_' + [guid]::NewGuid().ToString('N'))
$release = Join-Path $project 'release-velopack'
$dist = Join-Path $project 'dist\DrostSoundboard'
New-Item -ItemType Directory -Force -Path $werkmap | Out-Null
Push-Location $project
try {
    $config = Join-Path $werkmap 'releasebron.json'
    $configInhoud = @{repository_url=$bronurl; channel='beta'} | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($config, $configInhoud, [System.Text.UTF8Encoding]::new($false))

    Write-Host '1/5: afhankelijkheden voor releasebouwer installeren...'
    & $python -m pip install -r requirements.txt -r requirements-release.txt -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE-007: afhankelijkheden installeren is mislukt.' }
    Write-Host '2/5: volledige automatische tests draaien...'
    & $python -m unittest discover -s tests -q
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE-008: tests faalden; geen build gemaakt.' }

    Write-Host '3/5: zelfstandige vensterloze PyInstaller-app maken...'
    & $python -m PyInstaller `
        --onedir --windowed --noupx --clean --noconfirm `
        --name DrostSoundboard `
        --paths . `
        --add-data 'app/webinterface/statisch:app/webinterface/statisch' `
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
    if (-not $proces.WaitForExit(30000)) {
        Stop-Process -Id $proces.Id -Force -ErrorAction SilentlyContinue
        throw 'RELEASE-011: de EXE-smoketest duurde langer dan 30 seconden; de bouw stopt.'
    }
    $proces.Refresh()
    if ($proces.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $diagnose)) {
        throw 'RELEASE-012: de gebundelde EXE kon de eigen bestanden niet controleren.'
    }
    $status = Get-Content -LiteralPath $diagnose -Raw | ConvertFrom-Json
    if (-not $status.geslaagd) { throw ('RELEASE-017: smoketest faalde: ' + (Get-Content -LiteralPath $diagnose -Raw)) }
    if ($bronurl -and -not $status.repository_geverifieerd) {
        throw 'RELEASE-013: de ingevoegde GitHub-repository is niet in de EXE aanwezig.'
    }
    Write-Host 'EXE-smoketest geslaagd.' -ForegroundColor Green
    if ($AlleenExe) {
        Write-Host "Losse EXE-testbuild: $exe" -ForegroundColor Green
        Write-Warning 'Dit is nog GEEN automatische-updateinstallatie. Deel de map dist niet als publieke release.'
        return
    }

    Write-Host '5/5: Velopack Setup.exe en updatepakketten bouwen...'
    $vpk = (Get-Command vpk.exe -ErrorAction SilentlyContinue | Select-Object -First 1)
    $vpkPad = if ($vpk) { $vpk.Source } else { Join-Path $env:USERPROFILE '.dotnet\tools\vpk.exe' }
    if (-not (Test-Path -LiteralPath $vpkPad -PathType Leaf)) {
        throw 'RELEASE-014: vpk ontbreekt. Installeer .NET SDK 8 en voer uit: dotnet tool install --global vpk --version 1.2.161'
    }
    New-Item -Path $release -ItemType Directory -Force | Out-Null
    & $vpkPad pack `
        --runtime win-x64 `
        --packId 'DrostSoundboard.Desktop' `
        --packVersion $versie `
        --packTitle 'DrostSoundboard' `
        --channel 'beta' `
        --packDir $dist `
        --mainExe 'DrostSoundboard.exe' `
        --outputDir $release
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE-015: Velopack kon de installer niet maken.' }
    $setups = @(Get-ChildItem -LiteralPath $release -Filter '*Setup.exe' -File)
    if ($setups.Count -eq 0) { throw 'RELEASE-016: de Velopack Setup.exe ontbreekt.' }

    $lijst = Join-Path $release 'SHA256SUMS.txt'
    $regels = @(Get-ChildItem -LiteralPath $release -File |
        Where-Object { $_.Name -ne 'SHA256SUMS.txt' } |
        ForEach-Object { $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); "$hash  $($_.Name)" })
    [System.IO.File]::WriteAllLines($lijst, $regels, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Setup en releasepakketten: $release" -ForegroundColor Green
    if (-not $bronurl) { Write-Warning 'Geen GitHubRepository opgegeven. Deze testinstaller kan nog NIET op updates controleren.' }
    Write-Warning 'Dit is een BETA. Eerst op Windows x64 testen, inclusief echte audio, update en deinstaller.'
    Write-Warning 'Code signing ontbreekt; SmartScreen kan waarschuwen. VB-CABLE moet apart worden geïnstalleerd.'
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $werkmap) {
        Remove-Item -LiteralPath $werkmap -Force -Recurse -ErrorAction SilentlyContinue
    }
}
