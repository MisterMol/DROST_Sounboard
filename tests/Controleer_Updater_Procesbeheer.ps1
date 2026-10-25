#requires -Version 5.1
<#
    Losse, niet-destructieve regressietests voor het updater-procesbeheer.
    Start in Windows PowerShell met:
    powershell.exe -NoProfile -File .\tests\Controleer_Updater_Procesbeheer.ps1

    Alle processen hieronder zijn nagebootst. Dit script stopt niets.
#>
$ErrorActionPreference = 'Stop'
$projectmap = 'C:\Gebruikers\Voorbeeld Gebruiker\Broncode\DrostSoundboard'
$pythonMetConsole = Join-Path $projectmap '.venv\Scripts\python.exe'
$pythonZonderConsole = Join-Path $projectmap '.venv\Scripts\pythonw.exe'
$startbestand = Join-Path $projectmap 'start_desktop.py'
$basisPythonMetConsole = 'C:\Python313\python.exe'
$basisPythonZonderConsole = 'C:\Python313\pythonw.exe'
$eigenWindowsSessie = 7

. (Join-Path (Split-Path -Parent $PSScriptRoot) 'Updater_Procesbeheer.ps1')

function Maak-NepProces([int] $nummer, [string] $exe, [string] $opdracht, [int] $sessie = 7) {
    return [pscustomobject]@{
        ProcessId = $nummer
        ExecutablePath = $exe
        CommandLine = $opdracht
        SessionId = $sessie
        CreationDate = [datetime]'2026-10-25T08:09:29'
    }
}
function Controleer([bool] $actueel, [bool] $verwacht, [string] $omschrijving) {
    if ($actueel -ne $verwacht) {
        throw "Test mislukt: $omschrijving (verwacht: $verwacht, gekregen: $actueel)"
    }
    Write-Host "OK: $omschrijving"
}

$aanroep = '"' + $pythonZonderConsole + '" "' + $startbestand + '"'
$kort = '"' + $pythonZonderConsole + '" start_desktop.py'
$launcher = Maak-NepProces 15420 $pythonZonderConsole $kort
$echteApp = Maak-NepProces 4344 $basisPythonZonderConsole $kort
$volledig = Maak-NepProces 4344 $basisPythonZonderConsole $aanroep

Controleer (Hoort-ProcesBijDitProject $launcher) $true 'venv-redirector wordt herkend'
Controleer (Hoort-ProcesBijDitProject $echteApp) $true 'base-Python-kind wordt herkend'
Controleer (Hoort-ProcesBijDitProject $volledig) $true 'absoluut pad met spaties werkt'

$anderProject = Maak-NepProces 3100 $basisPythonZonderConsole '"C:\AnderProject\.venv\Scripts\pythonw.exe" start_desktop.py'
Controleer (Hoort-ProcesBijDitProject $anderProject) $false 'ander Python-project blijft ongemoeid'

$andereApp = Maak-NepProces 3101 $basisPythonZonderConsole '"C:\Python313\pythonw.exe" "C:\AnderProject\start_desktop.py"'
Controleer (Hoort-ProcesBijDitProject $andereApp) $false 'andere start_desktop.py wordt geweigerd'

$verkeerdExe = Maak-NepProces 3102 'C:\Ander\pythonw.exe' $aanroep
Controleer (Hoort-ProcesBijDitProject $verkeerdExe) $false 'vreemde Python-installatie wordt geweigerd'

$verkeerdeSessie = Maak-NepProces 3103 $basisPythonZonderConsole $aanroep 8
Controleer (Hoort-ProcesBijDitProject $verkeerdeSessie) $false 'andere Windows-sessie blijft ongemoeid'

$verkeerdeBestandsnaam = Maak-NepProces 3104 $basisPythonZonderConsole ('"' + $pythonZonderConsole + '" start_desktop.py.backup')
Controleer (Hoort-ProcesBijDitProject $verkeerdeBestandsnaam) $false 'gelijke bestandsnaamprefix is niet voldoende'

$basisRelatief = Maak-NepProces 3105 $basisPythonZonderConsole '"C:\Python313\pythonw.exe" start_desktop.py'
Controleer (Hoort-ProcesBijDitProject $basisRelatief) $false 'rechtstreekse basis-Python met relatief pad is niet betrouwbaar'

$gevonden = @(Zoek-GecontroleerdProcesOpId @($launcher, $echteApp) 4344)
Controleer ($gevonden.Count -eq 1 -and $gevonden[0].ProcessId -eq 4344) $true 'werkelijke server-PID wint van de redirector'

$nietGevonden = @(Zoek-GecontroleerdProcesOpId @($launcher, $echteApp) 32000)
Controleer ($nietGevonden.Count -eq 0) $true 'onbekende server-PID wordt nooit goedgekeurd'

Write-Host 'Alle 11 procesherkenningstests zijn geslaagd.' -ForegroundColor Green
