#requires -Version 5.1
# Haal alleen de gecontroleerde normale DSP-motor uit de EIGEN officiële RC5-release.
# De grote AI-stemruntime en het startersoundpack zijn hiervoor niet nodig.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$uri = 'https://github.com/MisterMol/DROST_Sounboard/releases/download/v6.1.0-rc.5/DrostSoundboard.Desktop-beta-Setup.exe'
$shaSetup = 'ef471e36ad689e440afd5f2883b475d698443742b69ea921443cfc51969f08c0'
$shaDll = 'e3280a9d37a20fbbf28f59a564156af17411e90cf947d4b163ad617e5c8a4467'
$dest = Join-Path $project 'app\audio\native\win-x64\drost_stem.dll'
$startmap = Join-Path $env:TEMP ('DrostBouw_HerstelAudio_' + [guid]::NewGuid().ToString('N'))
$installmap = Join-Path $startmap 'RC5_Installatie'
$setup = Join-Path $startmap 'RC5_Setup.exe'

try {
    if (Test-Path -LiteralPath $dest -PathType Leaf) {
        if ((Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant() -eq $shaDll) {
            Write-Host 'De oorspronkelijke normale audiomotor is al aanwezig en gecontroleerd.'
            return
        }
        throw 'RELEASE-042: bestaande audiomotor wijkt af van het gecontroleerde RC5-bouwbestand.'
    }
    New-Item -ItemType Directory -Path $startmap -Force | Out-Null
    Write-Host 'RC5 Setup van eigen GitHub Release downloaden (alleen voor Windows-bouwrunner)...'
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $uri -OutFile $setup -UseBasicParsing
    $controle = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($controle -ne $shaSetup) {
        throw 'RELEASE-043: RC5 Setup heeft een andere SHA256. Uitvoering geweigerd.'
    }
    Write-Host 'Gecontroleerde RC5 Setup zonder gebruikersinterface uitpakken naar aparte tijdelijke map...'
    New-Item -ItemType Directory -Path $installmap -Force | Out-Null
    $proces = Start-Process -FilePath $setup -ArgumentList @('--silent', '--installto', ('"' + $installmap + '"')) -Wait -PassThru
    if ($null -eq $proces -or $proces.ExitCode -ne 0) {
        throw ('RELEASE-044: gecontroleerde RC5 Setup kon niet worden uitgepakt; foutcode ' + $proces.ExitCode)
    }
    $bron = Join-Path $installmap 'current\_internal\app\audio\native\win-x64\drost_stem.dll'
    if (-not (Test-Path -LiteralPath $bron -PathType Leaf)) {
        throw 'RELEASE-045: de officiële RC5 Setup heeft de verwachte DSP-DLL niet op de pakketlocatie.'
    }
    if ((Get-FileHash -LiteralPath $bron -Algorithm SHA256).Hash.ToLowerInvariant() -ne $shaDll) {
        throw 'RELEASE-046: de uitgepakte DLL verschilt van het oorspronkelijke stembouw-manifest.'
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
    Copy-Item -LiteralPath $bron -Destination $dest
    if ((Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $shaDll) {
        throw 'RELEASE-047: gekopieerde DSP-motor is beschadigd.'
    }
    Write-Host 'Normale DSP-motor gecontroleerd. Grote AI-stemmen worden niet meegeleverd.'
} finally {
    Remove-Item -LiteralPath $startmap -Recurse -Force -ErrorAction SilentlyContinue
}
