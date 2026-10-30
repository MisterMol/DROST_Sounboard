# DrostSoundboard vanaf een gepubliceerde GitHub Release installeren.
# Windows PowerShell 5.1 en PowerShell 7. Python is niet nodig.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repository = 'MisterMol/DROST_Sounboard'
$releasesPagina = "https://github.com/$repository/releases"
$api = "https://api.github.com/repos/$repository/releases?per_page=30"
$downloadMap = Join-Path $env:TEMP 'DrostSoundboard-Setup'

function Lees-Veld($object, [string]$naam) {
    # Een API-antwoord kan ook een foutobject zijn. Ontbrekende velden zijn geen crash.
    if ($null -eq $object) { return $null }
    $eigenschap = $object.PSObject.Properties[$naam]
    if ($null -eq $eigenschap) { return $null }
    return $eigenschap.Value
}

function Stop-Met-Uitleg([string]$bericht) {
    Write-Host ''
    Write-Host "Niet gelukt: $bericht" -ForegroundColor Yellow
    Write-Host "Bekijk de releases: $releasesPagina"
    exit 1
}

function Haal-Releases-Op {
    # Invoke-RestMethod + @() kan op Windows PowerShell een extra arraylaag geven.
    # Daarom lezen we de JSON zelf uit en normaliseren we die expliciet.
    try {
        $antwoord = Invoke-WebRequest -Uri $api -Headers @{
            'User-Agent' = 'DrostSoundboard-Installatiestarter'
            'Accept' = 'application/vnd.github+json'
        } -TimeoutSec 30 -UseBasicParsing -ErrorAction Stop
    } catch {
        $status = $null
        $foutRespons = Lees-Veld $_.Exception 'Response'
        if ($null -ne $foutRespons) {
            try { $status = [int](Lees-Veld $foutRespons 'StatusCode') } catch { }
        }
        if ($status -eq 403 -or $status -eq 429) {
            throw 'GitHub weigert tijdelijk het API-verzoek, mogelijk door de verzoeklimiet. Probeer later opnieuw of download de Setup via Releases.'
        }
        if ($status -eq 404) {
            throw 'De GitHub-releaselijst is niet beschikbaar. Controleer of de repository en release openbaar zijn.'
        }
        throw "GitHub kon niet worden bereikt: $($_.Exception.Message)"
    }

    try {
        $inhoud = ConvertFrom-Json -InputObject ([string]$antwoord.Content) -ErrorAction Stop
    } catch {
        throw 'GitHub stuurde geen leesbare JSON terug. Probeer het later opnieuw.'
    }

    $apiFout = [string](Lees-Veld $inhoud 'message')
    if ($apiFout) {
        throw "GitHub antwoordde: $apiFout"
    }

    $releases = New-Object System.Collections.ArrayList
    # Zowel geen, een of meerdere releases werken, ook bij geneste arrayuitvoer.
    foreach ($item in $inhoud) {
        if ($null -eq $item) { continue }
        if ($item -is [System.Array]) {
            foreach ($subitem in $item) {
                if ($null -ne $subitem) { [void]$releases.Add($subitem) }
            }
        } else {
            [void]$releases.Add($item)
        }
    }

    foreach ($release in $releases) {
        if (-not (Lees-Veld $release 'tag_name')) {
            throw 'GitHub gaf een onverwacht releaseantwoord zonder versietag. Er wordt niets gedownload.'
        }
    }
    return ,$releases
}

function Kies-Nieuwste-Release($releases) {
    $gepubliceerd = @($releases | Where-Object {
        -not [bool](Lees-Veld $_ 'draft')
    } | Sort-Object -Property @{ Expression = { [string](Lees-Veld $_ 'published_at') } } -Descending)
    if ($gepubliceerd.Count -eq 0) { return $null }
    return $gepubliceerd[0]
}

function Kies-Setup($release) {
    $assets = @(Lees-Veld $release 'assets')
    $kandidaten = @($assets | Where-Object {
        $naam = [string](Lees-Veld $_ 'name')
        $status = [string](Lees-Veld $_ 'state')
        $naam -match '^DrostSoundboard(?:\.[A-Za-z0-9_-]+)*-Setup\.exe$' -and
        ($status -eq 'uploaded' -or -not $status)
    })
    if ($kandidaten.Count -eq 0) { return $null }
    $voorkeur = @($kandidaten | Where-Object {
        [string](Lees-Veld $_ 'name') -eq 'DrostSoundboard.Desktop-beta-Setup.exe'
    })
    if ($voorkeur.Count -gt 0) { return $voorkeur[0] }
    return $kandidaten[0]
}

function Controleer-Exe([string]$pad) {
    $bestand = [IO.File]::OpenRead($pad)
    try {
        if ($bestand.ReadByte() -ne 77 -or $bestand.ReadByte() -ne 90) {
            throw 'Het gedownloade bestand heeft geen geldige Windows-EXE-header.'
        }
    } finally {
        $bestand.Dispose()
    }
}

try {
    Write-Host ''
    Write-Host 'DrostSoundboard installeren vanaf GitHub' -ForegroundColor Cyan
    Write-Host 'De Setup wordt opgehaald van de officiele GitHub-repository.'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    Write-Host 'Controleren welke Windows Setup beschikbaar is...'
    $releases = Haal-Releases-Op
    $release = Kies-Nieuwste-Release $releases
    if ($null -eq $release) {
        Stop-Met-Uitleg 'Er is nog geen gepubliceerde GitHub Release. Maak eerst een release aan en voeg de Windows Setup.exe toe.'
    }

    $tag = [string](Lees-Veld $release 'tag_name')
    $releaseNaam = [string](Lees-Veld $release 'name')
    $asset = Kies-Setup $release
    if ($null -eq $asset) {
        Write-Host ''
        Write-Host "Release: $releaseNaam (tag $tag)" -ForegroundColor Cyan
        Write-Host 'Deze release bevat nog geen DrostSoundboard Setup.exe.'
        Write-Host 'De standaard Source code ZIP en TAR.GZ zijn geen Windows-installer.'
        Write-Host 'Beheerder: open Edit release en voeg het gebouwde bestand toe:'
        Write-Host 'DrostSoundboard.Desktop-beta-Setup.exe'
        Write-Host "Release bewerken: https://github.com/$repository/releases/tag/$tag"
        Stop-Met-Uitleg 'Eerst de Windows Setup uploaden naar de nieuwste release.'
    }

    $url = [string](Lees-Veld $asset 'browser_download_url')
    if (-not $url.StartsWith("https://github.com/$repository/releases/download/", [StringComparison]::OrdinalIgnoreCase)) {
        throw 'De downloadlink verwijst niet naar deze GitHub-repository.'
    }
    $grootte = [long](Lees-Veld $asset 'size')
    if ($grootte -lt 10000000) {
        throw 'De Windows Setup op GitHub is onverwacht klein. Controleer het releasebestand.'
    }
    $bestandsnaam = [IO.Path]::GetFileName([string](Lees-Veld $asset 'name'))
    $veiligeTag = $tag -replace '[^A-Za-z0-9._-]', '_'
    $doelMap = Join-Path $downloadMap $veiligeTag
    $doel = Join-Path $doelMap $bestandsnaam
    New-Item -ItemType Directory -Path $doelMap -Force | Out-Null

    Write-Host "Release: $releaseNaam (tag $tag)"
    Write-Host "Bestand: $bestandsnaam"
    Write-Host "Grootte: $([math]::Round($grootte / 1MB, 1)) MB"

    $verwachteHash = ''
    $digest = [string](Lees-Veld $asset 'digest')
    if ($digest -match '^sha256:([a-fA-F0-9]{64})$') {
        $verwachteHash = $Matches[1].ToLowerInvariant()
    }

    $magHergebruiken = $false
    if ((Test-Path -LiteralPath $doel -PathType Leaf) -and $verwachteHash) {
        if ((Get-Item -LiteralPath $doel).Length -eq $grootte) {
            $magHergebruiken = ((Get-FileHash -LiteralPath $doel -Algorithm SHA256).Hash.ToLowerInvariant() -eq $verwachteHash)
        }
    }

    if (-not $magHergebruiken) {
        $tijdelijk = "$doel.download"
        Remove-Item -LiteralPath $tijdelijk -Force -ErrorAction SilentlyContinue
        Write-Host 'Setup downloaden...'
        try {
            Invoke-WebRequest -Uri $url -Headers @{ 'User-Agent' = 'DrostSoundboard-Installatiestarter' } -OutFile $tijdelijk -UseBasicParsing -TimeoutSec 900 -ErrorAction Stop
            if ((Get-Item -LiteralPath $tijdelijk).Length -ne $grootte) {
                throw 'De download is onvolledig: de bestandsgrootte wijkt af.'
            }
            Controleer-Exe $tijdelijk
            $werkelijkeHash = (Get-FileHash -LiteralPath $tijdelijk -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($verwachteHash -and $werkelijkeHash -ne $verwachteHash) {
                throw 'De SHA256-hash van de download komt niet overeen met GitHub.'
            }
            Move-Item -LiteralPath $tijdelijk -Destination $doel -Force
        } catch {
            Remove-Item -LiteralPath $tijdelijk -Force -ErrorAction SilentlyContinue
            throw
        }
    }
    Controleer-Exe $doel

    Write-Host ''
    Write-Host 'Download voltooid.' -ForegroundColor Green
    Write-Host "Bestand: $doel"
    Write-Host "SHA256: $((Get-FileHash -LiteralPath $doel -Algorithm SHA256).Hash)"
    if (-not $verwachteHash) {
        Write-Host 'GitHub gaf geen SHA256-controlewaarde op. Alleen formaat, grootte en EXE-header zijn gecontroleerd.'
    }
    Write-Host 'Deze hobbyapp is nog niet digitaal ondertekend. Windows kan waarschuwen.'
    Write-Host ''
    $keuze = Read-Host 'De Windows Setup starten? Typ JA'
    if ($keuze -ne 'JA') {
        Write-Host 'De Setup is gedownload en kan later handmatig worden gestart.'
        exit 0
    }
    $proces = Start-Process -FilePath $doel -Wait -PassThru
    if ($proces.ExitCode -ne 0) {
        throw "De Windows Setup eindigde met foutcode $($proces.ExitCode)."
    }
    Write-Host 'De Windows Setup is afgesloten. Controleer of DrostSoundboard goed start.'
    Write-Host 'VB-CABLE is een aparte afhankelijkheid voor Uitzenden: https://vb-audio.com/Cable/'
    Write-Host 'Voor Preview en bibliotheekbeheer is VB-CABLE niet nodig.'
} catch {
    Stop-Met-Uitleg $_.Exception.Message
}
