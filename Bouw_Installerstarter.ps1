#requires -Version 5.1
[CmdletBinding()]
param([switch] $RC6Bundel)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Gebruik Windows.' }
if ($PSVersionTable.PSEdition -ne 'Desktop') { throw 'Gebruik Windows PowerShell 5.1.' }
$root = Split-Path -Parent $PSCommandPath
$dir = Join-Path $root 'dist-installerstarter'
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$target = Join-Path $dir 'DrostSoundboard-Installeren.exe'
if (Test-Path $target) { Remove-Item $target -Force }
$bronnen = @(
    (Join-Path $root 'hulpmiddelen\installerstarter\DrostInstallerStarter.cs'),
    (Join-Path $root 'hulpmiddelen\installerstarter\StartersoundpackAutomatisch.cs'),
    (Join-Path $root 'hulpmiddelen\installerstarter\GebundeldeSetup.cs')
)
$assemblies = @('System','System.Core','System.Drawing','System.Windows.Forms','System.Net.Http','System.Web.Extensions')
if ($RC6Bundel) {
    $parameters = New-Object System.CodeDom.Compiler.CompilerParameters
    $parameters.CompilerOptions = '/define:RC6_BUNDEL'
    Add-Type -Path $bronnen -OutputAssembly $target -OutputType WindowsApplication -ReferencedAssemblies $assemblies -CompilerParameters $parameters
} else {
    Add-Type -Path $bronnen -OutputAssembly $target -OutputType WindowsApplication -ReferencedAssemblies $assemblies
}
if (-not (Test-Path $target)) { throw 'Starter kon niet worden gebouwd.' }
Get-FileHash -Path $target -Algorithm SHA256
Write-Warning 'De Windows-installer is nog niet digitaal ondertekend. Test eerst op een Windows-pc.'
