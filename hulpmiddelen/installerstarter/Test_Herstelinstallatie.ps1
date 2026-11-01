#requires -Version 5.1
# Test op een schone GitHub Windows-runner dat dezelfde RC6 Setup tweemaal
# kan installeren en dat DrostSoundboard-gebruikersdata behouden blijven.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Setup)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath $Setup -PathType Leaf)) {
    throw 'HERSTEL-001: de te testen RC6 Setup ontbreekt.'
}
$testBasis = Join-Path $env:TEMP ('DrostHerstelTest_' + [guid]::NewGuid().ToString('N'))
$installatie = Join-Path $testBasis 'Installatie'
$lokaleData = Join-Path $env:LOCALAPPDATA 'DrostSoundboard'
$marker = Join-Path $lokaleData ('hersteltest_' + [guid]::NewGuid().ToString('N') + '.txt')
$updater = Join-Path $installatie 'Update.exe'
$appExe = Join-Path $installatie 'current\DrostSoundboard.exe'
$setupVolledig = (Resolve-Path -LiteralPath $Setup).Path

function Voer-SetupUit([string]$fase) {
    Write-Host ('Windows hersteltest: ' + $fase)
    $args = @('--silent', '--installto', ('"' + $installatie + '"'))
    $process = Start-Process -FilePath $setupVolledig -ArgumentList $args -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw ('HERSTEL-002: ' + $fase + ' eindigde met foutcode ' + $process.ExitCode)
    }
    if (-not (Test-Path -LiteralPath $updater -PathType Leaf) -or
        -not (Test-Path -LiteralPath $appExe -PathType Leaf)) {
        throw ('HERSTEL-003: ' + $fase + ' leverde geen complete Velopack-installatie op.')
    }
}

try {
    New-Item -ItemType Directory -Force -Path $testBasis | Out-Null
    Voer-SetupUit 'eerste stille installatie'
    New-Item -ItemType Directory -Force -Path $lokaleData | Out-Null
    [IO.File]::WriteAllText($marker, 'Persoonlijke gegevens moeten herinstallatie overleven.')
    Voer-SetupUit 'dezelfde RC6 opnieuw installeren zonder uninstall'
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
        throw 'HERSTEL-004: een gebruikersbestand is tijdens opnieuw installeren verdwenen.'
    }
    if ((Get-Content -LiteralPath $marker -Raw) -ne 'Persoonlijke gegevens moeten herinstallatie overleven.') {
        throw 'HERSTEL-005: het gebruikersbestand is gewijzigd.'
    }
    Write-Host 'Windows hersteltest geslaagd. Twee installaties, één versie, bibliotheekmap intact.'
} finally {
    if (Test-Path -LiteralPath $updater -PathType Leaf) {
        try {
            $weg = Start-Process -FilePath $updater -ArgumentList @('uninstall', '--silent') -Wait -PassThru
            if ($weg.ExitCode -ne 0) {
                Write-Warning ('Testinstallatie-uninstaller gaf foutcode ' + $weg.ExitCode)
            }
        } catch {
            Write-Warning ('Testinstallatie opruimen: ' + $_.Exception.Message)
        }
    }
    if (Test-Path -LiteralPath $marker -PathType Leaf) {
        Remove-Item -LiteralPath $marker -Force
    }
    if (Test-Path -LiteralPath $testBasis) {
        Remove-Item -LiteralPath $testBasis -Force -Recurse -ErrorAction SilentlyContinue
    }
}
