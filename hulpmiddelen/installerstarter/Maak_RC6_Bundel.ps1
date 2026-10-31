#requires -Version 5.1
# Verpak de zojuist gebouwde, geverifieerde RC6 Velopack Setup in de zichtbare
# Windows-installer. De gebruiker ontvangt slechts EEN .exe en geen ZIP.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$bouwmappen = @(Get-ChildItem (Join-Path $project 'release-velopack') -Directory -Filter 'Bouw-6.1.0-rc.6-*')
if ($bouwmappen.Count -ne 1) { throw 'INSTALL-060: verwacht precies een gecontroleerde RC6-bouwmap.' }
$setup = Join-Path $bouwmappen[0].FullName 'DrostSoundboard.Desktop-beta-Setup.exe'
$basis = Join-Path $project 'dist-installerstarter\DrostSoundboard-Installeren.exe'
$uitvoer = Join-Path $project 'dist-installerstarter\DrostSoundboard-Installeren-RC6-Test.exe'
if (-not (Test-Path -LiteralPath $setup -PathType Leaf) -or
    -not (Test-Path -LiteralPath $basis -PathType Leaf)) {
    throw 'INSTALL-061: Windows Setup of gecompileerde installer ontbreekt.'
}
$grootte = (Get-Item -LiteralPath $setup).Length
if ($grootte -lt 10MB -or $grootte -gt 300MB) {
    throw 'INSTALL-062: onverwachte omvang RC6 Setup, bundel afgebroken.'
}
$hash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
$kenmerk = 'DROSTPKGv000001!'
if ($kenmerk.Length -ne 16) { throw 'INSTALL-063: ongeldige bundelhandtekening.' }
Copy-Item -LiteralPath $basis -Destination $uitvoer -Force
$dest = $null
$bron = $null
try {
    $dest = [IO.File]::Open($uitvoer, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $bron = [IO.File]::OpenRead($setup)
    $buffer = New-Object byte[] (1024 * 1024)
    $geschreven = [long]0
    while (($aantal = $bron.Read($buffer, 0, $buffer.Length)) -gt 0) {
        $dest.Write($buffer, 0, $aantal)
        $geschreven += $aantal
    }
    if ($geschreven -ne $grootte) { throw 'INSTALL-064: niet alle Setup-bytes zijn ingesloten.' }
    $shaBytes = New-Object byte[] 32
    for ($i = 0; $i -lt 32; $i++) {
        $shaBytes[$i] = [Convert]::ToByte($hash.Substring($i * 2, 2), 16)
    }
    $dest.Write($shaBytes, 0, $shaBytes.Length)
    $lengteBytes = [BitConverter]::GetBytes([long]$grootte)
    $dest.Write($lengteBytes, 0, $lengteBytes.Length)
    $merkBytes = [Text.Encoding]::ASCII.GetBytes($kenmerk)
    $dest.Write($merkBytes, 0, $merkBytes.Length)
} finally {
    if ($null -ne $bron) { $bron.Dispose() }
    if ($null -ne $dest) { $dest.Dispose() }
}
Write-Host ('Zichtbare RC6-installatie-EXE gemaakt: ' + $uitvoer)
Write-Host ('Complete bestandsgrootte: ' + [math]::Round((Get-Item $uitvoer).Length / 1MB, 1) + ' MiB')
Write-Host ('Ingesloten Setup SHA256: ' + $hash)
