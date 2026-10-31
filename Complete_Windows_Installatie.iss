; Complete offline release wrapper. No second user-facing Setup download.
[Setup]
AppName=DrostSoundboard Complete
AppVersion=6.1.0 RC5
AppPublisher=MisterMol
CreateAppDir=no
Uninstallable=no
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
DisableReadyPage=yes
OutputDir=dist-complete\uitvoer
OutputBaseFilename=DrostSoundboard-Complete-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
[Files]
Source: "dist-complete\payload\DrostSoundboard.Desktop-beta-Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "dist-complete\payload\DrostSoundboard_startersoundpack.zip"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "dist-complete\payload\DrostSoundboard-Complete-Runner.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "dist-complete\payload\pakket.json"; DestDir: "{tmp}"; Flags: deleteafterinstall
[Run]
Filename: "{tmp}\DrostSoundboard-Complete-Runner.exe"; Description: "DrostSoundboard en startersoundpack installeren"; Flags: waituntilterminated
