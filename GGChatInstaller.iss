[Setup]
AppName=GG Chat
AppVersion=2.0.3
AppPublisher=GG Chat
AppPublisherURL=https://github.com/LeoPiro/ggchat_py
AppSupportURL=https://github.com/LeoPiro/ggchat_py
AppUpdatesURL=https://github.com/LeoPiro/ggchat_py
DefaultDirName={localappdata}\GGChat
DefaultGroupName=GG Chat
OutputBaseFilename=GGChatInstaller
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
SetupIconFile=gg_fUv_icon.ico
DisableWelcomePage=yes
; Upgrade handling
UninstallDisplayName=GG Chat
AppId={{A3B1C2D4-E5F6-7890-ABCD-EF1234567890}
VersionInfoVersion=2.0.3
VersionInfoCompany=GG Chat
VersionInfoDescription=GG Chat Application
VersionInfoCopyright=Copyright (C) 2025

[Files]
Source: "dist\GGChat.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\webview_launcher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "alert.wav"; DestDir: "{app}"
Source: "notify.wav"; DestDir: "{app}"
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
