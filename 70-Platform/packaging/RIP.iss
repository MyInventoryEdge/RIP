#define AppVersion "0.4.0"

[Setup]
AppId={{8E1E24D0-5692-4A1C-919D-704A14C2F38F}
AppName=RIP
AppVersion={#AppVersion}
AppPublisher=RIP
AppPublisherURL=https://rip.local
DefaultDirName={autopf}\RIP
DefaultGroupName=RIP
DisableProgramGroupPage=yes
OutputDir=C:\RIP\Releases
OutputBaseFilename=RIP-Setup-{#AppVersion}
SetupIconFile=..\assets\rip.ico
UninstallDisplayIcon={app}\RIP.exe
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
Compression=lzma2
SolidCompression=yes

[Files]
Source: "..\build-output\internal\RIP.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\RIP"; Filename: "{app}\RIP.exe"; IconFilename: "{app}\RIP.exe"
Name: "{autoprograms}\RIP\RIP"; Filename: "{app}\RIP.exe"; IconFilename: "{app}\RIP.exe"

[Run]
Filename: "{app}\RIP.exe"; Description: "Launch RIP"; Flags: nowait postinstall skipifsilent
