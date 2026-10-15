; Inno Setup — bộ cài Windows cho CapCut Draft Studio
; Biên dịch: ISCC.exe /DMyAppVersion=0.4.0 installer\setup.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.5.6"
#endif
#define MyAppName "CapCut Draft Studio"
#define MyAppExeName "CapCut Draft Studio.exe"
#define MyAppPublisher "LEO"

[Setup]
AppId={{8C2F1A64-6B2E-4E0E-9E2A-CAPCUTDS0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\CapCutDraftStudio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=CapCutDraftStudio-{#MyAppVersion}-windows-setup
SetupIconFile=..\assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Cai cho rieng nguoi dung dang dang nhap: khong hien bang UAC, va thu muc cai
; nam trong %LOCALAPPDATA%\Programs nen ghi duoc. Nguoi dung van chon cai cho
; toan may duoc o bang dau tien neu muon.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
; Neu tool van dang mo (vd bam cai ban moi tu cua so Explorer), bo cai tu dong
; tool truoc khi ghi de thay vi bao loi "file dang duoc su dung".
CloseApplications=force
RestartApplications=no

[Languages]
Name: "vi"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tao bieu tuong ngoai man hinh"; GroupDescription: "Tuy chon:"

[InstallDelete]
; Ban 0.5.3+ dong goi dang thu muc: xoa thu vien cua ban cu truoc khi chep ban moi
; de khong con file .pyd/.dll cu lan vao. "bin" cu (ffmpeg) nay da nam trong _internal.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\bin"

[Files]
; Ca thu muc onedir: CapCut Draft Studio.exe + _internal\ (Python, thu vien, ffmpeg, assets)
Source: "..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Go cai dat {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Mo {#MyAppName} ngay"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallDelete]
Type: filesandordirs; Name: "{app}\updates"
