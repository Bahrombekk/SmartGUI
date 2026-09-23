; SafeZone — Inno Setup installer.
; Avval PyInstaller build (dist\SafeZone), keyin: ISCC installer\SafeZone.iss
; Natija: installer\Output\SafeZone-Setup-<versiya>.exe (bitta fayl).
;
; Dastur {app} (Program Files) ga o'rnatiladi. Yoziladigan ma'lumotlar
; (settings.json, smartgui.db, logs, violations) C:\ProgramData\SafeZone da
; saqlanadi — app/shared/paths.py shu yo'lni tanlaydi.

#define AppName      "SafeZone"
#define AppVersion   "1.1.0"
#define AppPublisher "SafeZone"
#define AppExe       "SafeZone.exe"
#define DistDir      "..\dist\SafeZone"

[Setup]
AppId={{6B1E6E0A-4C3A-4B7E-9C51-5AFE20E0A001}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=SafeZone-Setup-{#AppVersion}
SetupIconFile=..\images\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/normal
SolidCompression=no
LZMAUseSeparateProcess=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Dirs]
; Oddiy foydalanuvchi ham sozlama/baza/rasmlarni yoza olishi uchun
Name: "{commonappdata}\SafeZone"; Permissions: users-modify

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Uninstall C:\ProgramData\SafeZone ni (sozlamalar, baza, buzilish rasmlari)
; ataylab o'chirmaydi — qayta o'rnatganda ma'lumotlar saqlanib qoladi.
