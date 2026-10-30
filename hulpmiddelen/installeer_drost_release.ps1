# DrostSoundboard vanuit iedere Windows-map installeren, ook zonder Git.
# Haalt uitsluitend een Setup op uit de publieke releases van dit project.
# Windows PowerShell 5.1 en PowerShell 7. Python is niet nodig.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repository = 'MisterMol/DROST_Sounboard'
$releasesPagina = "https://github.com/$repository/releases"
$api = "https://api.github.com/repos/$repository/releases?per_page=30"

function Lees-Veld($object, [string]$naam) {
    # Een API-response mag een lege lijst of foutobject zijn.
    if ($null -eq $object) { return $null }
    $eigenschap = $object.PSObject.Properties[$naam]
    if ($null -eq $eigenschap) { return $null }
    return $eigenschap.Value
}

function Stop-Met-Uitleg([string]$melding) {
    Write-Host ''
    Write-Host "Installatie niet gestart: $melding" -ForegroundColor Yellow
    Write-Host "GitHub Releases: $releasesPagina"
    exit 1
}

function Lees-GitHub-Releases {
    $headers = @{
        'Accept' = 'application/vnd.github+json'
        'User-Agent' = 'DrostSoundboard-Windows-Installatiestarter'
        'X-GitHub-Api-Version' = '2022-11-28'
    }
    try {
        # Content zelf parsen: Invoke-RestMethod heeft in Windows PowerShell 5.1
        # afwijkend pipelinegedrag bij arrays met slechts een release.
        $antwoord = Invoke-WebRequest -Uri $api -Headers $headers -UseBasicParsing -TimeoutSec 30 -ErrorAction Stop
    } catch {
        $statusCode = $null
        $response = Lees-Veld $_.Exception 'Response'
        if ($null -ne $response) {
            try { $statusCode = [int](Lees-Veld $response 'StatusCode') } catch { }
        }
        if ($statusCode -eq 403 -or $statusCode -eq 429) {
            throw 'GitHub heeft de API-verzoeken tijdelijk begrensd. Open Releases zelf of probeer later opnieuw.'
        }
        if ($statusCode -eq 404) {
            throw 'De GitHub-repository of releases zijn niet publiek bereikbaar.'
        }
        throw "GitHub is niet bereikbaar: $($_.Exception.Message)"
    }
    try {
        $gegevens = ConvertFrom-Json -InputObject ([string]$antwoord.Content) -ErrorAction Stop
    } catch {
        throw 'GitHub stuurde geen geldige JSON terug. Er is niets gedownload.'
    }
    if ($null -eq $gegevens) { throw 'GitHub gaf een leeg antwoord terug.' }
    $bericht = [string](Lees-Veld $gegevens 'message')
    if ($bericht) { throw "GitHub antwoordde met een fout: $bericht" }

    $gevonden = New-Object System.Collections.ArrayList
    foreach ($item in $gegevens) {
        if ($null -eq $item) { continue }
        # Vang ook een onbedoeld geneste lijst op, zonder een API-fout als release aan te zien.
        if ($item -is [System.Array]) {
            foreach ($subitem in $item) {
                if ($null -ne $subitem) { [void]$gevonden.Add($subitem) }
            }
        } else {
            [void]$gevonden.Add($item)
        }
    }
    foreach ($item in $gevonden) {
        if (-not (Lees-Veld $item 'tag_name')) {
            throw 'Het GitHub-antwoord bevat geen geldige releasetags.'
        }
    }
    return ,$gevonden.ToArray()
}

function Kies-Release($releases) {
    # Ga nooit stilzwijgend terug naar een oudere installer als de nieuwste ontbreekt.
    $gepubliceerd = @($releases | Where-Object {
        -not [bool](Lees-Veld $_ 'draft')
    } | Sort-Object -Property @{ Expression = { [string](Lees-Veld $_ 'published_at') } } -Descending)
    if ($gepubliceerd.Count -eq 0) { return $null }
    return $gepubliceerd[0]
}

function Kies-Installer($release) {
    $assetsWaarde = Lees-Veld $release 'assets'
    if ($null -eq $assetsWaarde) { return $null }
    $assets = @($assetsWaarde)
    $gevonden = @($assets | Where-Object {
        $naam = [string](Lees-Veld $_ 'name')
        $status = [string](Lees-Veld $_ 'state')
        ($naam -match '^DrostSoundboard(?:\.[a-zA-Z0-9_-]+)*-Setup\.exe$') -and
        ($status -eq 'uploaded' -or -not $status)
    })
    if ($gevonden.Count -eq 0) { return $null }
    $voorkeur = @($gevonden | Where-Object {
        [string](Lees-Veld $_ 'name') -eq 'DrostSoundboard.Desktop-beta-Setup.exe'
    })
    if ($voorkeur.Count -gt 0) { return $voorkeur[0] }
    return $gevonden[0]
}

function Controleer-WindowsExe([string]$pad) {
    # Alleen een MZ-header is niet genoeg: valideer ook PE\0\0.
    $stream = [IO.File]::OpenRead($pad)
    try {
        $reader = [IO.BinaryReader]::new($stream)
        if ($reader.ReadByte() -ne 0x4D -or $reader.ReadByte() -ne 0x5A) {
            throw 'Het opgehaalde bestand is geen Windows-uitvoerbaar bestand (MZ ontbreekt).'
        }
        if ($stream.Length -lt 1024) { throw 'De Setup is ongeldig of onvolledig.' }
        $stream.Position = 0x3c
        $pePositie = $reader.ReadInt32()
        if ($pePositie -lt 64 -or $pePositie -gt ($stream.Length - 4)) {
            throw 'De Setup bevat geen geldige PE-headerpositie.'
        }
        $stream.Position = $pePositie
        if ($reader.ReadByte() -ne 0x50 -or $reader.ReadByte() -ne 0x45 -or
            $reader.ReadByte() -ne 0 -or $reader.ReadByte() -ne 0) {
            throw 'De Setup bevat geen geldige PE-header.'
        }
    } finally {
        $stream.Dispose()
    }
}

try {
    Write-Host ''
    Write-Host 'DrostSoundboard installeren' -ForegroundColor Cyan
    Write-Host 'De Windows Setup komt uitsluitend uit de officiele GitHub-releases.'
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'Deze Windows Setup is gebouwd voor een 64-bits Windows-systeem.'
    }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    Write-Host 'Releases controleren...'
    $releases = Lees-GitHub-Releases
    $release = Kies-Release $releases
    if ($null -eq $release) {
        Stop-Met-Uitleg 'Er is nog geen gepubliceerde release met een Windows Setup.'
    }
    $tag = [string](Lees-Veld $release 'tag_name')
    $naamRelease = [string](Lees-Veld $release 'name')
    $installer = Kies-Installer $release
    if ($null -eq $installer) {
        Write-Host "De nieuwste release is '$naamRelease' (tag $tag)."
        Write-Host 'Hier staat geen Windows Setup.exe bij. Source code ZIP/TAR is geen installer.'
        Write-Host 'De beheerder moet bij Edit release een DrostSoundboard...-Setup.exe uploaden.'
        Stop-Met-Uitleg 'Er is nog geen installer om te downloaden.'
    }

    $url = [string](Lees-Veld $installer 'browser_download_url')
    $prefix = "https://github.com/$repository/releases/download/"
    if (-not $url.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'De Setup-downloadlink verwijst niet naar de verwachte GitHub-repository.'
    }
    $bestandsnaam = [string](Lees-Veld $installer 'name')
    if ([IO.Path]::GetFileName($bestandsnaam) -ne $bestandsnaam) {
        throw 'GitHub stuurde een onveilige bestandsnaam.'
    }
    $grootte = [long](Lees-Veld $installer 'size')
    if ($grootte -lt 10000000) {
        throw 'De Setup is kleiner dan verwacht. Controleer het bestand in de release.'
    }

    # Windows kiest zelf de gebruikersmap. Dit script kent geen vaste gebruikersnaam.
    $basis = [Environment]::GetFolderPath('LocalApplicationData')
    if ([string]::IsNullOrWhiteSpace($basis)) { $basis = [IO.Path]::GetTempPath() }
    $map = Join-Path (Join-Path $basis 'DrostSoundboard\Installers') ($tag -replace '[^a-zA-Z0-9._-]', '_')
    New-Item -ItemType Directory -Force -Path $map | Out-Null
    $doel = Join-Path $map $bestandsnaam

    $digest = [string](Lees-Veld $installer 'digest')
    $verwachteHash = ''
    if ($digest -match '^sha256:([A-Fa-f0-9]{64})$') {
        $verwachteHash = $Matches[1].ToLowerInvariant()
    }
    $hergebruik = $false
    if ((Test-Path -LiteralPath $doel -PathType Leaf) -and $verwachteHash) {
        $bestaand = Get-Item -LiteralPath $doel
        if ($bestaand.Length -eq $grootte) {
            $hergebruik = ((Get-FileHash -LiteralPath $doel -Algorithm SHA256).Hash.ToLowerInvariant() -eq $verwachteHash)
        }
    }

    Write-Host "Release: $naamRelease ($tag)"
    Write-Host "Setup: $bestandsnaam ($([math]::Round($grootte / 1MB, 1)) MB)"
    if (-not $hergebruik) {
        $tijdelijk = "$doel.download"
        Remove-Item -LiteralPath $tijdelijk -Force -ErrorAction SilentlyContinue
        Write-Host 'Downloaden vanuit GitHub...'
        try {
            Invoke-WebRequest -Uri $url -OutFile $tijdelijk -UseBasicParsing -TimeoutSec 900 -Headers @{
                'User-Agent' = 'DrostSoundboard-Windows-Installatiestarter'
            } -ErrorAction Stop
            if ((Get-Item -LiteralPath $tijdelijk).Length -ne $grootte) {
                throw 'De download is onvolledig: bestandsgrootte komt niet overeen.'
            }
            Controleer-WindowsExe $tijdelijk
            $werkelijkeHash = (Get-FileHash -LiteralPath $tijdelijk -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($verwachteHash -and $werkelijkeHash -ne $verwachteHash) {
                throw 'De SHA256-controle van de GitHub-release is mislukt.'
            }
            Move-Item -LiteralPath $tijdelijk -Destination $doel -Force
        } catch {
            Remove-Item -LiteralPath $tijdelijk -Force -ErrorAction SilentlyContinue
            throw
        }
    }
    Controleer-WindowsExe $doel
    $hash = (Get-FileHash -LiteralPath $doel -Algorithm SHA256).Hash
    Write-Host ''
    Write-Host 'De Windows Setup is gedownload.' -ForegroundColor Green
    Write-Host "Locatie: $doel"
    Write-Host "SHA256: $hash"
    if (-not $verwachteHash) {
        Write-Host 'GitHub gaf geen losse SHA256-controlewaarde. Controleer de releasebron voor installatie.'
    }
    Write-Host 'Deze hobbyapp is niet digitaal ondertekend. Windows kan een waarschuwing tonen.'
    Write-Host ''
    $bevestig = Read-Host 'Setup.exe nu starten? Typ JA'
    if ($bevestig -cne 'JA') {
        Write-Host 'Niet gestart. Je kunt de gedownloade Setup later zelf openen.'
        exit 0
    }
    $proces = Start-Process -FilePath $doel -Wait -PassThru
    if ($proces.ExitCode -ne 0) {
        throw "De Setup is geeindigd met foutcode $($proces.ExitCode)."
    }
    Write-Host 'De Setup is gesloten. Controleer of de app goed is geinstalleerd en start.'
    Write-Host 'VB-CABLE is een aparte afhankelijkheid voor Uitzenden: https://vb-audio.com/Cable/'
    Write-Host 'Preview en bibliotheekbeheer werken ook zonder VB-CABLE.'
} catch {
    Stop-Met-Uitleg $_.Exception.Message
}
