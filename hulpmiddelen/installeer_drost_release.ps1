# DrostSoundboard installatie via een officiele GitHub Release.
# PowerShell 5.1 en hoger. Geen beheerder nodig om de Setup te downloaden.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'Continue'

$repository = 'MisterMol/DROST_Sounboard'
$api = "https://api.github.com/repos/$repository/releases?per_page=30"
$releasesPagina = "https://github.com/$repository/releases"
$downloadMap = Join-Path $env:TEMP 'DrostSoundboard-Setup'

function Toon-Fout([string]$bericht) {
    Write-Host ''
    Write-Host "Niet gelukt: $bericht" -ForegroundColor Red
    Write-Host "Releases: $releasesPagina"
    exit 1
}

function Kies-Setup($publicaties) {
    # Gebruik de nieuwste gepubliceerde release die daadwerkelijk een Windows Setup heeft.
    $beschikbaar = @($publicaties | Where-Object { -not $_.draft } | Sort-Object -Property published_at -Descending)
    foreach ($publicatie in $beschikbaar) {
        $kandidaten = @($publicatie.assets | Where-Object {
            $_.state -eq 'uploaded' -and $_.name -match '^DrostSoundboard(?:\.[A-Za-z0-9_-]+)*-Setup\.exe$'
        })
        if ($kandidaten.Count -gt 0) {
            $gekozen = $kandidaten | Where-Object { $_.name -eq 'DrostSoundboard.Desktop-beta-Setup.exe' } | Select-Object -First 1
            if (-not $gekozen) { $gekozen = $kandidaten | Select-Object -First 1 }
            return [pscustomobject]@{ Release = $publicatie; Bestand = $gekozen }
        }
    }
    return $null
}

try {
    Write-Host ''
    Write-Host 'DrostSoundboard installeren vanaf GitHub' -ForegroundColor Cyan
    Write-Host 'De installer wordt alleen opgehaald van de officiele repository.'

    # Zorg dat Windows PowerShell 5.1 HTTPS met TLS 1.2 kan gebruiken.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $headers = @{
        'User-Agent' = 'DrostSoundboard-Installatiestarter'
        'Accept' = 'application/vnd.github+json'
    }
    Write-Host 'Controleren welke Windows Setup beschikbaar is...'
    $publicaties = @(Invoke-RestMethod -Uri $api -Headers $headers -TimeoutSec 30)
    $keuze = Kies-Setup $publicaties
    if (-not $keuze) {
        Toon-Fout 'Er is nog geen Windows Setup bij GitHub Releases geplaatst. Alleen broncode-ZIP-bestanden zijn niet voldoende.'
    }

    $asset = $keuze.Bestand
    $publicatie = $keuze.Release
    $url = [string]$asset.browser_download_url
    if (-not $url.StartsWith("https://github.com/$repository/releases/download/", [StringComparison]::OrdinalIgnoreCase)) {
        Toon-Fout 'De downloadlink komt niet overeen met de verwachte GitHub-repository.'
    }
    if ($asset.size -lt 10000000) {
        Toon-Fout 'De Setup op GitHub is onverwacht klein. Controleer de Release.'
    }

    $bestandsnaam = [IO.Path]::GetFileName([string]$asset.name)
    $doelmap = Join-Path $downloadMap ([string]$publicatie.tag_name -replace '[^A-Za-z0-9._-]', '_')
    $doel = Join-Path $doelmap $bestandsnaam
    New-Item -Path $doelmap -ItemType Directory -Force | Out-Null

    Write-Host "Release: $($publicatie.name)"
    Write-Host "Bestand: $bestandsnaam"
    Write-Host "Omvang: $([math]::Round($asset.size / 1MB, 1)) MB"
    Write-Host 'Downloaden...'

    # Hergebruik de download alleen als GitHub de SHA256 opgeeft en die overeenkomt.
    $verwachteHash = ''
    if ($asset.PSObject.Properties.Name -contains 'digest') {
        if ($asset.digest -and ([string]$asset.digest) -match '^sha256:([a-fA-F0-9]{64})$') {
            $verwachteHash = $Matches[1].ToLowerInvariant()
        }
    }
    $hergebruik = $false
    if ((Test-Path -LiteralPath $doel -PathType Leaf) -and $verwachteHash) {
        if ((Get-Item -LiteralPath $doel).Length -eq [int64]$asset.size) {
            $hergebruik = ((Get-FileHash -LiteralPath $doel -Algorithm SHA256).Hash.ToLowerInvariant() -eq $verwachteHash)
        }
    }
    if (-not $hergebruik) {
        $tijdelijk = "$doel.download"
        Remove-Item -LiteralPath $tijdelijk -Force -ErrorAction SilentlyContinue
        try {
            Invoke-WebRequest -Uri $url -Headers @{ 'User-Agent' = 'DrostSoundboard-Installatiestarter' } -OutFile $tijdelijk -UseBasicParsing -TimeoutSec 900
            if ((Get-Item -LiteralPath $tijdelijk).Length -ne [int64]$asset.size) {
                throw 'De bestandsgrootte verschilt van de GitHub-release. De download is mogelijk onvolledig.'
            }
            $hash = (Get-FileHash -LiteralPath $tijdelijk -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($verwachteHash -and $hash -ne $verwachteHash) {
                throw 'De SHA256-controle van GitHub komt niet overeen met de download.'
            }
            $stream = [IO.File]::OpenRead($tijdelijk)
            try {
                if ($stream.ReadByte() -ne 77 -or $stream.ReadByte() -ne 90) {
                    throw 'Het opgehaalde bestand is geen herkenbare Windows-EXE.'
                }
            } finally {
                $stream.Dispose()
            }
            Move-Item -LiteralPath $tijdelijk -Destination $doel -Force
        } catch {
            Remove-Item -LiteralPath $tijdelijk -Force -ErrorAction SilentlyContinue
            throw
        }
    }

    # Controleer ook bij een eerder gedownload bestand de EXE-header.
    $stream = [IO.File]::OpenRead($doel)
    try {
        if ($stream.ReadByte() -ne 77 -or $stream.ReadByte() -ne 90) {
            Toon-Fout 'De Setup is geen herkenbaar uitvoerbaar Windows-bestand.'
        }
    } finally {
        $stream.Dispose()
    }

    Write-Host ''
    Write-Host 'Download voltooid.' -ForegroundColor Green
    Write-Host "Locatie: $doel"
    Write-Host "SHA256: $((Get-FileHash -LiteralPath $doel -Algorithm SHA256).Hash)"
    if (-not $verwachteHash) {
        Write-Host 'GitHub gaf geen SHA256 op. De download is wel op grootte en EXE-header gecontroleerd.'
    }
    Write-Host 'Let op: deze hobbyapp is nog niet digitaal ondertekend. Windows kan een waarschuwing geven.'
    Write-Host ''
    $antwoord = Read-Host 'De Windows Setup nu starten? Typ JA'
    if ($antwoord -ne 'JA') {
        Write-Host 'De Setup is gedownload. Je kunt hem later zelf openen.'
        exit 0
    }

    Start-Process -FilePath $doel -Wait
    Write-Host ''
    Write-Host 'Voor Uitzenden via de virtuele microfoon is VB-CABLE apart nodig:'
    Write-Host 'https://vb-audio.com/Cable/'
    Write-Host 'Preview en bibliotheekbeheer werken ook zonder VB-CABLE.'
} catch {
    Toon-Fout $_.Exception.Message
}
