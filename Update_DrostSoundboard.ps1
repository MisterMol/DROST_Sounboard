#requires -Version 5.1
<#
.SYNOPSIS
    Werk DrostSoundboard bij vanuit een gecontroleerd ZIP-bestand in Downloads.
.DESCRIPTION
    Deze ontwikkel-updater vraagt eerst toestemming, stopt uitsluitend de
    bijbehorende Python-desktopprocessen, bewaart gewijzigde bestanden,
    installeert de update, draait de tests en start de app opnieuw.

    Waarom niet zomaar het hele ZIP-bestand over de projectmap kopieren?
    Omdat we de oude bestanden bij een mislukte test precies moeten kunnen
    herstellen, zonder .venv, gebruikersdata of andere projecten te raken.

    Bedoeld voor broncode-updates tijdens ontwikkeling. De uiteindelijke
    publieke installer zal ondertekende en gecontroleerde releases gebruiken.
#>
[CmdletBinding()]
param(
    [string] $UpdateBestand = '',
    [switch] $NietOpnieuwStarten,
    [switch] $AlleenProcescontrole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# De updater ligt in de projectmap. Zo zijn er geen vaste gebruikersnamen of schijfletters nodig.
$projectmap = (Resolve-Path -LiteralPath $PSScriptRoot).Path.TrimEnd('\')
$pythonMetConsole = Join-Path $projectmap '.venv\Scripts\python.exe'
$pythonZonderConsole = Join-Path $projectmap '.venv\Scripts\pythonw.exe'
$startbestand = Join-Path $projectmap 'start_desktop.py'
$downloads = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Downloads'
$appgegevens = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'DrostSoundboard'
$eigenWindowsSessie = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
$updatebeheer = Join-Path $appgegevens 'updates'
$datumEnId = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$logmap = Join-Path $updatebeheer 'logboeken'
$reservekopieMap = Join-Path $updatebeheer ('reservekopien\' + $datumEnId)
$uitpakmap = Join-Path $env:TEMP ('DrostSoundboard_Update_' + $datumEnId)
$testUitvoer = Join-Path $logmap ('tests_' + $datumEnId + '_uitvoer.txt')
$testFouten = Join-Path $logmap ('tests_' + $datumEnId + '_meldingen.txt')
$transcriptBestand = Join-Path $logmap ('update_' + $datumEnId + '.txt')
$transcriptGestart = $false
$vergrendelingVanUpdater = $null

$geraaktePaden = [System.Collections.Generic.List[string]]::new()
$bronBestanden = @()
$bestandenGekopieerd = $false
$appDraaideVoorUpdate = $false
$allesGelukt = $false

function Toon-Bericht([string] $tekst, [string] $kleur = 'Gray') {
    Write-Host $tekst -ForegroundColor $kleur
}

# Bereken de echte interpreterpaden uit de venv-configuratie. Python 3.13
# start via een redirector een extra proces vanuit deze basisinstallatie.
$basisPythonMetConsole = ''
$basisPythonZonderConsole = ''
$venvConfiguratie = Join-Path $projectmap '.venv\pyvenv.cfg'
if (Test-Path -LiteralPath $venvConfiguratie -PathType Leaf) {
    foreach ($regel in @(Get-Content -LiteralPath $venvConfiguratie -Encoding UTF8)) {
        if ($regel -match '^\s*home\s*=\s*(.+?)\s*$') {
            $basisPythonMetConsole = Join-Path $Matches[1] 'python.exe'
            $basisPythonZonderConsole = Join-Path $Matches[1] 'pythonw.exe'
            break
        }
    }
}
. (Join-Path $PSScriptRoot 'Updater_Procesbeheer.ps1')

function Controleer-UpdateArchief([string] $zipPad) {
    <#
      ZIP-inhoud eerst controleren. Zo kan een verkeerd archief niet buiten
      de projectmap schrijven of lokale instellingen en .venv overschrijven.
    #>
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archief = [System.IO.Compression.ZipFile]::OpenRead($zipPad)
    try {
        if ($archief.Entries.Count -gt 5000) {
            throw 'Dit ZIP-bestand heeft onverwacht veel bestanden.'
        }
        [long]$totaal = 0
        $gevondenBestanden = 0
        $gezien = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
        foreach ($onderdeel in $archief.Entries) {
            $naam = $onderdeel.FullName.Replace('\', '/')
            if (-not $naam.StartsWith('DrostSoundboard/', [System.StringComparison]::Ordinal)) {
                throw "Ongeldige mapstructuur in ZIP: $naam"
            }
            $relatief = $naam.Substring('DrostSoundboard/'.Length)
            if (-not $relatief -or $relatief.EndsWith('/')) { continue }
            $delen = $relatief.Split('/')
            if (($delen -contains '..') -or ($delen -contains '.') -or
                ($delen -contains '') -or ($relatief -match '[<>:"|?*]')) {
                throw "Ongeldig bestandspad in ZIP: $naam"
            }
            foreach ($deel in $delen) {
                if ($deel -match '[. ]$' -or $deel -match '(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$') {
                    throw "Windows kan dit bestandspad niet veilig verwerken: $naam"
                }
            }
            if (-not $gezien.Add($relatief)) {
                throw "Dubbele bestandsnaam in ZIP (Windows is niet hoofdlettergevoelig): $naam"
            }
            if ($delen[0] -in @('.git', '.venv', 'dist', 'build', 'release') -or
                $delen[0] -eq '__pycache__' -or
                $delen[0] -eq 'gebruikersgegevens') {
                throw "ZIP probeert beschermde map te wijzigen: $naam"
            }
            # Unix-symlinks horen niet in een Windows-broncodepatch thuis.
            $bestandsoort = ($onderdeel.ExternalAttributes -shr 16) -band 61440
            if ($bestandsoort -eq 40960) {
                throw "Symbolische link is niet toegestaan in een update: $naam"
            }
            $totaal += $onderdeel.Length
            $gevondenBestanden++
        }
        if ($gevondenBestanden -eq 0 -or $totaal -gt 536870912) {
            throw 'Het ZIP-bestand is leeg of uitzonderlijk groot voor een broncode-update.'
        }
        return $gevondenBestanden
    } finally {
        $archief.Dispose()
    }
}

function Zet-AangepasteBestandenTerug {
    <#
      Herstel alleen bestanden die deze update heeft geraakt. Bestonden ze
      eerder niet, dan verwijderen we ze. Zo blijft een mislukte update niet
      half aanwezig en blijven alle andere bestanden ongemoeid.
    #>
    Toon-Bericht 'Oorspronkelijke bestanden worden teruggezet...' 'Yellow'
    foreach ($relatief in $geraaktePaden) {
        $doel = Join-Path $projectmap $relatief
        $vorige = Join-Path (Join-Path $reservekopieMap 'gewijzigde_bestanden') $relatief
        if (Test-Path -LiteralPath $vorige -PathType Leaf) {
            $doelmap = Split-Path -Parent $doel
            New-Item -Path $doelmap -ItemType Directory -Force | Out-Null
            Copy-Item -LiteralPath $vorige -Destination $doel -Force
        } elseif (Test-Path -LiteralPath $doel -PathType Leaf) {
            Remove-Item -LiteralPath $doel -Force
        }
    }
}

function Start-DesktopApp {
    if (-not (Test-Path -LiteralPath $pythonZonderConsole -PathType Leaf)) {
        throw 'pythonw.exe ontbreekt. Installeer eerst de ontwikkelomgeving.'
    }
    $argument = '"' + $startbestand + '"'
    return Start-Process -FilePath $pythonZonderConsole -ArgumentList $argument `
        -WorkingDirectory $projectmap -PassThru
}

function Lees-VersieUitGeinstalleerdeBroncode {
    <#
      Lees de exacte tekstversie uit de broncode die zojuist is gekopieerd.
      We controleren niet alleen of een poort reageert: een OUDE server kan
      dezelfde poort bedienen en toch de verkeerde code draaien.
    #>
    $bron = Join-Path $projectmap 'app\diagnostiek\logboek.py'
    if (-not (Test-Path -LiteralPath $bron -PathType Leaf)) {
        throw 'Versiebestand app\diagnostiek\logboek.py ontbreekt.'
    }
    $tekst = [System.IO.File]::ReadAllText($bron, [System.Text.Encoding]::UTF8)
    $gevonden = [regex]::Match($tekst, '(?m)^\s*VERSIE_VAN_DE_APP\s*=\s*["'']([^"''\r\n]+)["'']')
    if (-not $gevonden.Success) {
        throw 'De appversie is niet gevonden. Herstartcontrole afgebroken in plaats van een onbekende versie goed te keuren.'
    }
    return $gevonden.Groups[1].Value
}

function Controleer-NieuweDesktopApp([datetime] $gestartNa, [int] $startProcesId, [string] $verwachteVersie) {
    <#
      De venv-launcher en de Python-server hebben soms verschillende PIDs.
      Lees de echte server-PID uit het statusbestand, verifieer die tegen
      de volledige gecontroleerde Windows-proceslijst en controleer daarna
      via localhost de exacte serverversie. Een oude status mag niet tellen.
    #>
    $statusbestand = Join-Path $appgegevens 'actieve_desktopinstantie.json'
    $laatsteFout = 'Er is nog geen bevestigde desktopserver gevonden.'
    for ($poging = 0; $poging -lt 50; $poging++) {
        Start-Sleep -Milliseconds 400
        try {
            if (-not (Test-Path -LiteralPath $statusbestand -PathType Leaf)) {
                $laatsteFout = 'Het desktopstatusbestand is nog niet gemaakt.'
                continue
            }
            $bestand = Get-Item -LiteralPath $statusbestand -ErrorAction Stop
            if ($bestand.LastWriteTimeUtc -lt $gestartNa.ToUniversalTime().AddSeconds(-2)) {
                $laatsteFout = 'Het desktopstatusbestand is nog van voor deze herstart.'
                continue
            }
            $instantie = Get-Content -LiteralPath $statusbestand -Raw -Encoding UTF8 | ConvertFrom-Json
            $procesNummer = [int]$instantie.proces_id
            if ($procesNummer -le 0) {
                $laatsteFout = 'Ongeldig procesnummer in het desktopstatusbestand.'
                continue
            }
            $actueel = @(Geef-DrostSoundboardProcessen)
            $gevonden = @(Zoek-GecontroleerdProcesOpId $actueel $procesNummer)
            if ($gevonden.Count -ne 1) {
                $laatsteFout = "Statusbestand noemt proces $procesNummer, maar dat is geen gecontroleerd desktopproces van dit project."
                continue
            }
            $gevondenProces = $gevonden[0]
            $procesStart = [datetime]$gevondenProces.CreationDate
            if ($procesStart -lt $gestartNa.AddSeconds(-3)) {
                $laatsteFout = "Proces $procesNummer is al gestart voordat de update klaar was."
                continue
            }
            $poort = [int]$instantie.poort
            if ($poort -lt 1 -or $poort -gt 65535) {
                $laatsteFout = 'De lokaal gepubliceerde poort is ongeldig.'
                continue
            }
            $url = "http://127.0.0.1:$poort/api/versie"
            $antwoord = Invoke-RestMethod -Uri $url -TimeoutSec 2 -ErrorAction Stop
            if ([int]$antwoord.proces_id -ne $procesNummer) {
                $laatsteFout = 'Het API-antwoord hoort bij een ander proces dan het desktopstatusbestand.'
                continue
            }
            if ([string]$antwoord.versie -cne $verwachteVersie) {
                $laatsteFout = "Verkeerde versie actief: '$($antwoord.versie)' in plaats van '$verwachteVersie'."
                continue
            }
            $weerGevonden = @(Geef-DrostSoundboardProcessen | Where-Object { Is-HetzelfdeProces $gevondenProces $_ })
            if ($weerGevonden.Count -eq 0) {
                $laatsteFout = 'Het desktopproces stopte tijdens de bevestiging.'
                continue
            }
            if ($startProcesId -ne $procesNummer) {
                Toon-Bericht "Python-starter $startProcesId en desktopserver $procesNummer zijn verschillende processen. Dit is normaal." 'DarkGray'
            }
            return $antwoord
        } catch {
            $laatsteFout = $_.Exception.Message
        }
    }
    throw "Nieuwe desktopapp is niet bevestigd. Verwachte versie: $verwachteVersie. Laatste controle: $laatsteFout"
}

function Toon-Procescontrole {
    <#
      Diagnose zonder iets te installeren of af te sluiten. Geschikt om
      vooraf en na een update te zien of het goede proces wordt gevonden.
    #>
    $gevonden = @(Geef-DrostSoundboardProcessen)
    if ($gevonden.Count -eq 0) {
        Toon-Bericht 'Geen draaiend DrostSoundboard-desktopproces van dit project.' 'Yellow'
        return
    }
    Toon-Bericht "Gevonden DrostSoundboard-processen: $($gevonden.Count)" 'Cyan'
    foreach ($proces in $gevonden) {
        Toon-Bericht "Proces $($proces.ProcessId) | Sessie $($proces.SessionId) | Gestart: $($proces.CreationDate)"
    }
    $statusbestand = Join-Path $appgegevens 'actieve_desktopinstantie.json'
    if (-not (Test-Path -LiteralPath $statusbestand -PathType Leaf)) {
        Toon-Bericht 'Geen actief desktopstatusbestand gevonden.' 'Yellow'
        return
    }
    try {
        $instantie = Get-Content -LiteralPath $statusbestand -Raw -Encoding UTF8 | ConvertFrom-Json
        $matches = @($gevonden | Where-Object { [int]$_.ProcessId -eq [int]$instantie.proces_id })
        if ($matches.Count -eq 0) {
            Toon-Bericht 'Statusbestand wijst niet naar een gecontroleerd projectproces.' 'Yellow'
            return
        }
        $poort = [int]$instantie.poort
        if ($poort -lt 1 -or $poort -gt 65535) { throw 'Ongeldige poort in statusbestand.' }
        $antwoord = Invoke-RestMethod -Uri "http://127.0.0.1:$poort/api/versie" -TimeoutSec 3
        if ([int]$antwoord.proces_id -ne [int]$instantie.proces_id) {
            throw 'Desktopstatus en HTTP-proces komen niet overeen.'
        }
        Toon-Bericht "Actieve versie: $($antwoord.versie) | PID $($antwoord.proces_id) | Poort $poort" 'Green'
    } catch {
        Toon-Bericht "Geen bevestigde versie via de API: $($_.Exception.Message)" 'Yellow'
    }
}

try {
    if (-not (Test-Path -LiteralPath $pythonMetConsole -PathType Leaf)) {
        throw 'De Python-ontwikkelomgeving ontbreekt. Voer eerst Installeer_ontwikkelomgeving.bat uit.'
    }
    if (-not (Test-Path -LiteralPath $startbestand -PathType Leaf)) {
        throw 'start_desktop.py ontbreekt. Start de updater vanuit je DrostSoundboard-projectmap.'
    }
    New-Item -Path $updatebeheer -ItemType Directory -Force | Out-Null
    # Een tweede updater mag nooit tegelijk bestanden vervangen.
    $vergrendelbestand = Join-Path $updatebeheer 'bijwerken.lock'
    try {
        $vergrendelingVanUpdater = [System.IO.File]::Open(
            $vergrendelbestand,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    } catch [System.IO.IOException] {
        throw 'Er draait al een DrostSoundboard-update. Sluit die eerst af.'
    }
    New-Item -Path $logmap -ItemType Directory -Force | Out-Null
    if (-not $AlleenProcescontrole) { New-Item -Path $reservekopieMap -ItemType Directory -Force | Out-Null }
    Start-Transcript -Path $transcriptBestand -Force | Out-Null
    $transcriptGestart = $true

    Toon-Bericht 'DrostSoundboard automatisch bijwerken' 'Cyan'
    Toon-Bericht "Project: $projectmap"

    if ($AlleenProcescontrole) {
        Toon-Bericht 'Alleen procescontrole: geen projectbestanden of processen worden gewijzigd.' 'Cyan'
        Toon-Procescontrole
        $allesGelukt = $true
    } else {
        if ($UpdateBestand) {
        if (-not (Test-Path -LiteralPath $UpdateBestand -PathType Leaf)) {
            throw "Updatebestand ontbreekt: $UpdateBestand"
        }
        $zip = Get-Item -LiteralPath $UpdateBestand
    } else {
        if (-not (Test-Path -LiteralPath $downloads -PathType Container)) {
            throw "Downloads-map ontbreekt: $downloads"
        }
        $mogelijk = @(Get-ChildItem -LiteralPath $downloads -File -Filter 'DrostSoundboard*.zip' |
            Where-Object { $_.Name -match '(?i)(?:Update|Herstel|Patch)(?:\s*\(\d+\))?\.zip$' } |
            Sort-Object LastWriteTime -Descending)
        if ($mogelijk.Count -eq 0) {
            throw 'Geen DrostSoundboard-update in Downloads gevonden. Download eerst het update-ZIP-bestand.'
        }
        $zip = $mogelijk[0]
    }
    Toon-Bericht "Geselecteerd: $($zip.Name)" 'White'
    Toon-Bericht "SHA256: $((Get-FileHash -LiteralPath $zip.FullName -Algorithm SHA256).Hash)"

    # Voorkom per ongeluk een oudere patch te installeren wanneer Downloads
    # meerdere ZIP-bestanden bevat. De versie uit de bestandsnaam is alleen
    # een extra controle, geen vervanging voor bron- of ondertekeningcontrole.
    $gevondenZipVersie = [regex]::Match($zip.Name, 'DrostSoundboard_(\d+)_(\d+)_(\d+)')
    $versiebestand = Join-Path $projectmap 'app\diagnostiek\logboek.py'
    if ($gevondenZipVersie.Success -and (Test-Path -LiteralPath $versiebestand)) {
        $versieTekst = Get-Content -LiteralPath $versiebestand -Encoding UTF8 -Raw
        $gevondenAppVersie = [regex]::Match($versieTekst, 'VERSIE_VAN_DE_APP\s*=\s*["''](\d+)\.(\d+)\.(\d+)')
        if ($gevondenAppVersie.Success) {
            $actueleVersie = [version](('{0}.{1}.{2}' -f $gevondenAppVersie.Groups[1].Value,
                $gevondenAppVersie.Groups[2].Value, $gevondenAppVersie.Groups[3].Value))
            $gevraagdeVersie = [version](('{0}.{1}.{2}' -f $gevondenZipVersie.Groups[1].Value,
                $gevondenZipVersie.Groups[2].Value, $gevondenZipVersie.Groups[3].Value))
            if ($gevraagdeVersie -lt $actueleVersie) {
                throw "De gekozen update ($gevraagdeVersie) is ouder dan de projectcode ($actueleVersie). Download de juiste update."
            }
        }
    }
    $aantal = Controleer-UpdateArchief $zip.FullName
    Toon-Bericht "ZIP gecontroleerd: $aantal bestanden."

    Toon-Bericht ''
    Toon-Bericht 'Let op: de virtuele microfoon stopt tijdelijk. Werk NIET bij tijdens een gesprek.' 'Yellow'
    $toestemming = Read-Host 'Type JA om deze update te installeren'
    if ($toestemming -cne 'JA') {
        Toon-Bericht 'Update geannuleerd; de applicatie is niet gewijzigd.'
        $allesGelukt = $true
    } else {
        $bronWasActief = @(Geef-DrostSoundboardProcessen).Count -gt 0
        $appDraaideVoorUpdate = $bronWasActief

        # Eerst de update in een aparte tijdelijke map klaarzetten.
        New-Item -Path $uitpakmap -ItemType Directory -Force | Out-Null
        Expand-Archive -LiteralPath $zip.FullName -DestinationPath $uitpakmap -Force
        $stageProject = Join-Path $uitpakmap 'DrostSoundboard'
        if (-not (Test-Path -LiteralPath $stageProject -PathType Container)) {
            throw 'De verwachte DrostSoundboard-map is niet gevonden in het ZIP-bestand.'
        }
        $stageProject = (Resolve-Path -LiteralPath $stageProject).Path.TrimEnd('\')
        $bronBestanden = @(Get-ChildItem -LiteralPath $stageProject -Recurse -File)
        if ($bronBestanden.Count -eq 0) { throw 'Geen bestanden om te installeren.' }

        [void](Sluit-AlleenDrostSoundboardAf)
        # Wacht even tot Windows de mutex en de mediabestanden vrijgeeft.
        Start-Sleep -Milliseconds 350

        Toon-Bericht 'Back-up maken van alle bestanden die deze update wijzigt...'
        foreach ($bestand in $bronBestanden) {
            $relatief = $bestand.FullName.Substring($stageProject.Length).TrimStart([char]'\', [char]'/')
            $doel = Join-Path $projectmap $relatief
            if (Test-Path -LiteralPath $doel -PathType Leaf) {
                $doelBackup = Join-Path (Join-Path $reservekopieMap 'gewijzigde_bestanden') $relatief
                New-Item -Path (Split-Path -Parent $doelBackup) -ItemType Directory -Force | Out-Null
                Copy-Item -LiteralPath $doel -Destination $doelBackup -Force
            }
        }
        Toon-Bericht 'Updatebestanden installeren...'
        foreach ($bestand in $bronBestanden) {
            $relatief = $bestand.FullName.Substring($stageProject.Length).TrimStart([char]'\', [char]'/')
            $doel = Join-Path $projectmap $relatief
            $geraaktePaden.Add($relatief)
            New-Item -Path (Split-Path -Parent $doel) -ItemType Directory -Force | Out-Null
            Copy-Item -LiteralPath $bestand.FullName -Destination $doel -Force
        }
        $bestandenGekopieerd = $true
        Toon-Bericht "Geinstalleerde bestanden: $($bronBestanden.Count)" 'Green'

        Toon-Bericht 'Automatische tests uitvoeren...'
        $testProces = Start-Process -FilePath $pythonMetConsole `
            -ArgumentList @('-m', 'unittest', 'discover', '-s', 'tests', '-q') `
            -WorkingDirectory $projectmap -NoNewWindow -Wait -PassThru `
            -RedirectStandardOutput $testUitvoer -RedirectStandardError $testFouten
        $testResultaat = Get-Content -LiteralPath $testFouten -Tail 12 -ErrorAction SilentlyContinue
        if ($testResultaat) { $testResultaat | ForEach-Object { Write-Host $_ } }
        if ($testProces.ExitCode -ne 0) {
            throw "De tests zijn mislukt met code $($testProces.ExitCode). Zie $testFouten."
        }
        Toon-Bericht 'Alle automatische tests zijn geslaagd.' 'Green'

        if (-not $NietOpnieuwStarten) {
            Toon-Bericht 'Nieuwe desktopapp starten...'
            $gestartVanaf = Get-Date
            $verwachteVersie = Lees-VersieUitGeinstalleerdeBroncode
            $nieuwProces = Start-DesktopApp
            $nieuweVersie = Controleer-NieuweDesktopApp $gestartVanaf $nieuwProces.Id $verwachteVersie
            Toon-Bericht "Nieuwe versie actief: $($nieuweVersie.versie), proces $($nieuweVersie.proces_id)" 'Green'
        }
        Toon-Bericht 'Bijwerken afgerond.' 'Green'
        Toon-Bericht "Back-up: $reservekopieMap"
        Toon-Bericht "Installatielog: $transcriptBestand"
        $allesGelukt = $true
    }
    } # Einde echte update; procescontrole wijzigt niets.
} catch {
    Toon-Bericht "Update mislukt: $($_.Exception.Message)" 'Red'
    if ($geraaktePaden.Count -gt 0) {
        try {
            # Ook het nieuwe (mislukte) desktopproces moet eerst echt weg zijn.
            [void](Sluit-AlleenDrostSoundboardAf)
            Zet-AangepasteBestandenTerug
            Toon-Bericht 'Vorige bestanden zijn hersteld.' 'Yellow'
        } catch {
            Toon-Bericht "Automatisch herstel is niet volledig gelukt: $($_.Exception.Message)" 'Red'
            Toon-Bericht "Bewaar de back-up in: $reservekopieMap" 'Yellow'
        }
    }
    if ($appDraaideVoorUpdate -and -not $NietOpnieuwStarten) {
        try {
            [void](Start-DesktopApp)
            Toon-Bericht 'De eerdere DrostSoundboard-versie is opnieuw gestart.' 'Yellow'
        } catch {
            Toon-Bericht 'Herstart van de vorige versie is mislukt. Controleer de softwarelogs.' 'Red'
        }
    }
    Toon-Bericht "Updatelog: $transcriptBestand" 'Yellow'
} finally {
    if (Test-Path -LiteralPath $uitpakmap -PathType Container) {
        Remove-Item -LiteralPath $uitpakmap -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($transcriptGestart) { Stop-Transcript | Out-Null }
    if ($null -ne $vergrendelingVanUpdater) { $vergrendelingVanUpdater.Dispose() }
}

if (-not $allesGelukt) { exit 1 }
exit 0
