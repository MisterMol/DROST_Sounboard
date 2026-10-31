#requires -Version 5.1
[CmdletBinding()]
param([switch]$SkipDownload)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:OS -ne 'Windows_NT') { throw 'Bouw alleen op Windows.' }
if($PSVersionTable.PSEdition -ne 'Desktop') { throw 'Bouw met Windows PowerShell 5.1.' }
$root=Split-Path -Parent $PSCommandPath
$payload=Join-Path $root 'dist-complete\payload'
New-Item -ItemType Directory -Force -Path $payload | Out-Null
$tag='v6.1.0-rc.5'
$assets=@(
    @{naam='DrostSoundboard.Desktop-beta-Setup.exe';hash='ef471e36ad689e440afd5f2883b475d698443742b69ea921443cfc51969f08c0'},
    @{naam='DrostSoundboard_startersoundpack.zip';hash='e470cc3c03ea87027adbaa04e1bcedc3a414fa3d9da057778dcfd3fe2dda17a6'}
)
foreach($asset in $assets){
    $destination=Join-Path $payload $asset.naam
    if(-not $SkipDownload){
        Write-Host "Downloaden: $($asset.naam)"
        $url="https://github.com/MisterMol/DROST_Sounboard/releases/download/$tag/$($asset.naam)"
        Invoke-WebRequest -Uri $url -OutFile $destination -UseBasicParsing
    }
    if(-not (Test-Path -LiteralPath $destination -PathType Leaf)) { throw "Ontbrekend: $destination" }
    $digest=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if($digest -ne $asset.hash){throw "SHA256 komt niet overeen: $($asset.naam)"}
}
$manifest=@{release_tag=$tag;setup_sha256=$assets[0].hash;soundpack_sha256=$assets[1].hash} | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $payload 'pakket.json'),$manifest,[System.Text.UTF8Encoding]::new($false))
$runner=Join-Path $payload 'DrostSoundboard-Complete-Runner.exe'
if(Test-Path -LiteralPath $runner){Remove-Item -LiteralPath $runner -Force}
Add-Type -Path (Join-Path $root 'hulpmiddelen\complete_installer\DrostCompleteInstallatie.cs') -OutputAssembly $runner -OutputType WindowsApplication -ReferencedAssemblies @('System','System.Core','System.Drawing','System.Windows.Forms','System.Net.Http','System.Web.Extensions')
if(-not (Test-Path -LiteralPath $runner -PathType Leaf)){throw 'Runner niet gebouwd'}
$iscc=@(
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Inno Setup 6\ISCC.exe')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if(-not $iscc) {throw 'Inno Setup 6 ontbreekt. Installeer deze eerst.'}
& $iscc (Join-Path $root 'Complete_Windows_Installatie.iss')
if($LASTEXITCODE -ne 0) {throw 'Inno Setup compileerfout'}
$output=Join-Path $root 'dist-complete\uitvoer\DrostSoundboard-Complete-Setup.exe'
if(-not (Test-Path -LiteralPath $output -PathType Leaf)) {throw "Pakket ontbreekt: $output"}
Write-Host ('Volledige installer: '+$output)
Get-FileHash -LiteralPath $output -Algorithm SHA256
