; Inno Setup script – builds dist\SpideySense-Setup.exe from dist\SpideySense\
;
;   python packaging\make_icons.py
;   pyinstaller packaging\spidey.spec --noconfirm
;   iscc /DAppVersion=1.0.0 packaging\windows\spidey.iss
;
; Per-user install (no admin prompt) into %LOCALAPPDATA%\Programs\SpideySense.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Spidey Sense"
#define AppExe "SpideySense.exe"

[Setup]
; Never change AppId – upgrades find the old install through it
AppId={{50577CA2-A80D-4FE1-A5E6-A92C44656B33}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Danish Prabhu
AppPublisherURL=https://github.com/Danishprabhu04/spidey_reminder
DefaultDirName={localappdata}\Programs\SpideySense
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=SpideySense-Setup
SetupIconFile=..\..\build\icons\spidey.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Close a running Spidey before upgrading his files
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Start Spidey when I log in"; GroupDescription: "Extras:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Extras:"; Flags: unchecked

[Files]
Source: "..\..\dist\SpideySense\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same value the app's Settings → "Start Spidey when I log in" uses
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "SpideySense"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch Spidey now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "StopSpidey"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { Start-at-login may have been switched on later from Settings }
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'SpideySense');
end;
