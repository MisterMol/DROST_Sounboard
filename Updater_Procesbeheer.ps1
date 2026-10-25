#requires -Version 5.1
<#
    Procesherkenning voor de ontwikkel-updater.

    Windows Python 3.13 gebruikt in een venv een redirector. Die start een
    tweede python(w).exe vanuit de BASIS-installatie, maar behoudt de
    oorspronkelijke opdrachtregel met het venv-pad. Daarom mogen we
    ExecutablePath niet uitsluitend met .venv\Scripts vergelijken.

    Dit bestand wordt geladen door Update_DrostSoundboard.ps1 en kan zonder
    wijzigingen aan echte processen apart worden getest.
#>

function Is-HetzelfdeWindowsPad([string] $eerste, [string] $tweede) {
    if ([string]::IsNullOrWhiteSpace($eerste) -or [string]::IsNullOrWhiteSpace($tweede)) {
        return $false
    }
    try {
        $links = [System.IO.Path]::GetFullPath($eerste)
        $rechts = [System.IO.Path]::GetFullPath($tweede)
        return [string]::Equals($links, $rechts, [StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
}

function Geef-OpdrachtregelArgumenten([string] $opdrachtregel) {
    # De launcher en de applicatie gebruiken bestandsargumenten zonder
    # ingesloten aanhalingstekens. Deze parser ondersteunt paden met spaties.
    if ([string]::IsNullOrWhiteSpace($opdrachtregel)) { return @() }
    $resultaat = @()
    foreach ($deel in [regex]::Matches($opdrachtregel, '"[^\"]*"|\S+')) {
        $waarde = $deel.Value
        if ($waarde.Length -ge 2 -and $waarde.StartsWith('"') -and $waarde.EndsWith('"')) {
            $waarde = $waarde.Substring(1, $waarde.Length - 2)
        }
        $resultaat += $waarde
    }
    return $resultaat
}

function Is-StartbestandArgument([string] $argument) {
    if ([string]::IsNullOrWhiteSpace($argument)) { return $false }
    if ([System.IO.Path]::IsPathRooted($argument)) {
        return Is-HetzelfdeWindowsPad $argument $startbestand
    }
    # Alleen deze twee korte schrijfwijzen zijn mogelijk wanneer de
    # startscriptmap als WorkingDirectory is meegegeven.
    return ($argument -ieq 'start_desktop.py' -or $argument -ieq '.\start_desktop.py')
}

function Hoort-ProcesBijDitProject($proces) {
    if ($null -eq $proces) { return $false }
    if ([int]$proces.SessionId -ne $eigenWindowsSessie) { return $false }

    $bestand = [string]$proces.ExecutablePath
    if ([string]::IsNullOrWhiteSpace($bestand)) { return $false }
    $isVenvExe = (
        (Is-HetzelfdeWindowsPad $bestand $pythonMetConsole) -or
        (Is-HetzelfdeWindowsPad $bestand $pythonZonderConsole)
    )
    $isBasisExe = (
        (Is-HetzelfdeWindowsPad $bestand $basisPythonMetConsole) -or
        (Is-HetzelfdeWindowsPad $bestand $basisPythonZonderConsole)
    )
    if (-not ($isVenvExe -or $isBasisExe)) { return $false }

    $delen = @(Geef-OpdrachtregelArgumenten ([string]$proces.CommandLine))
    if ($delen.Count -lt 2) { return $false }

    $aangeroepenPython = [string]$delen[0]
    $isVenvOpdracht = (
        (Is-HetzelfdeWindowsPad $aangeroepenPython $pythonMetConsole) -or
        (Is-HetzelfdeWindowsPad $aangeroepenPython $pythonZonderConsole)
    )
    $isBasisOpdracht = (
        (Is-HetzelfdeWindowsPad $aangeroepenPython $basisPythonMetConsole) -or
        (Is-HetzelfdeWindowsPad $aangeroepenPython $basisPythonZonderConsole)
    )
    if (-not ($isVenvOpdracht -or $isBasisOpdracht)) { return $false }

    # Bij een aanroep vanuit de venv is de werkmap van de starter bekend.
    # Bij direct aangeroepen basis-Python eisen we een ABSOLUUT scriptpad.
    # Zo kan een ander project met een eigen start_desktop.py niet worden
    # aangezien voor deze installatie.
    $argument = [string]$delen[1]
    if (-not (Is-StartbestandArgument $argument)) { return $false }
    if ($isBasisOpdracht -and -not [System.IO.Path]::IsPathRooted($argument)) {
        return $false
    }
    return $true
}

function Geef-DrostSoundboardProcessen {
    $mogelijk = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction Stop)
    return @($mogelijk | Where-Object { Hoort-ProcesBijDitProject $_ })
}

function Is-HetzelfdeProces($verwacht, $actueel) {
    if ($null -eq $verwacht -or $null -eq $actueel) { return $false }
    if ([int]$verwacht.ProcessId -ne [int]$actueel.ProcessId) { return $false }
    if (-not (Hoort-ProcesBijDitProject $actueel)) { return $false }
    return [datetime]$verwacht.CreationDate -eq [datetime]$actueel.CreationDate
}

function Zoek-GecontroleerdProcesOpId([object[]] $processen, [int] $procesId) {
    # Een venv-redirector en de werkelijke desktopserver kunnen allebei
    # herkend worden. Kies de PID die de app ZELF publiceerde, niet de
    # toevallig eerste PID in de WMI-lijst.
    return @($processen | Where-Object { [int]$_.ProcessId -eq $procesId })
}

function Sluit-AlleenDrostSoundboardAf {
    $processen = @(Geef-DrostSoundboardProcessen)
    if ($processen.Count -eq 0) {
        Toon-Bericht 'Geen draaiend DrostSoundboard-proces van dit project gevonden.'
        return $false
    }
    # Stop de echte interpreter vóór de venv-redirector; de redirector
    # wacht immers op het kindproces en zal normaal zelf eindigen.
    $opVolgorde = @($processen | Sort-Object @{ Expression = {
        if ((Is-HetzelfdeWindowsPad ([string]$_.ExecutablePath) $pythonMetConsole) -or
            (Is-HetzelfdeWindowsPad ([string]$_.ExecutablePath) $pythonZonderConsole)) { 1 } else { 0 }
    } })
    foreach ($verwacht in $opVolgorde) {
        $nummer = [int]$verwacht.ProcessId
        $nogActief = @(Geef-DrostSoundboardProcessen | Where-Object { Is-HetzelfdeProces $verwacht $_ })
        if ($nogActief.Count -eq 0) { continue }
        Toon-Bericht "DrostSoundboard afsluiten (proces $nummer)." 'Yellow'
        try {
            $procesobject = Get-Process -Id $nummer -ErrorAction Stop
            $verschilInSeconden = [math]::Abs(($procesobject.StartTime - [datetime]$verwacht.CreationDate).TotalSeconds)
            if ($verschilInSeconden -gt 2) {
                throw "Proces-ID $nummer is inmiddels hergebruikt. Stoppen geweigerd."
            }
            Stop-Process -InputObject $procesobject -ErrorAction Stop
        } catch {
            $nogActief = @(Geef-DrostSoundboardProcessen | Where-Object { Is-HetzelfdeProces $verwacht $_ })
            if ($nogActief.Count -gt 0) { throw }
        }
    }
    for ($poging = 0; $poging -lt 40; $poging++) {
        if (@(Geef-DrostSoundboardProcessen).Count -eq 0) { return $true }
        Start-Sleep -Milliseconds 250
    }
    throw 'DrostSoundboard is nog actief. Update afgebroken om beschadiging van bestanden te voorkomen.'
}
