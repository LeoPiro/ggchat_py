[Setup]
AppName=GG Chat
AppVersion=1.0.0
DefaultDirName={localappdata}\GGChat
DefaultGroupName=GG Chat
OutputBaseFilename=GGChatInstaller
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
SetupIconFile=gg_fUv_icon.ico
DisableWelcomePage=yes

[Files]
Source: "dist\GGChat.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "alert.wav"; DestDir: "{app}"
Source: "notify.mp3"; DestDir: "{app}"
Source: "gg_fUv_icon.ico"; DestDir: "{app}"
; Include any other resource files you use

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"


[Icons]
Name: "{group}\GG Chat"; Filename: "{app}\GGChat.exe"
Name: "{group}\Uninstall GG Chat"; Filename: "{uninstallexe}"
Name: "{userdesktop}\GG Chat"; Filename: "{app}\GGChat.exe"; Tasks: desktopicon

[UninstallDelete]
Type: dirifempty; Name: "{app}"


[Run]
Filename: "{app}\GGChat.exe"; Description: "Launch GG Chat"; Flags: nowait postinstall skipifsilent
