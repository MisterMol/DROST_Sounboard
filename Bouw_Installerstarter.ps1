#requires -Version 5.1
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Gebruik Windows.' }
if ($PSVersionTable.PSEdition -ne 'Desktop') { throw 'Gebruik Windows PowerShell 5.1.' }
$root = Split-Path -Parent $PSCommandPath
$dir = Join-Path $root 'dist-installerstarter'
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$target = Join-Path $dir 'DrostSoundboard-Installeren.exe'
if (Test-Path $target) { Remove-Item $target -Force }
Add-Type -Path (Join-Path $root 'hulpmiddelen\installerstarter\DrostInstallerStarter.cs') -OutputAssembly $target -OutputType WindowsApplication -ReferencedAssemblies @('System','System.Core','System.Drawing','System.Windows.Forms','System.Net.Http','System.Web.Extensions')
if (-not (Test-Path $target)) { throw 'Starter kon niet worden gebouwd.' }
Get-FileHash -Path $target -Algorithm SHA256
Write-Warning 'Test de starter op Windows. De EXE is niet digitaal ondertekend.'
