; AI Meetings — InnoSetup 6 installer script
; Packages the PyInstaller-compiled AI_Meetings.exe
; Build: .\build_now.ps1  (from installer/ directory)
; Output: dist\AI_Meetings_Setup.exe

#define AppName      "AI Meetings"
#define AppVersion   "1.0"
#define AppPublisher "AI Meetings"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=AI_Meetings_Setup
SetupIconFile=assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
MinVersion=10.0.17763
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\AI_Meetings.exe
UninstallDisplayName={#AppName}
WizardImageFile=assets\wizard.bmp
WizardSmallImageFile=assets\icon_small.bmp
DisableWelcomePage=no
LicenseFile=..\LICENSE.txt
ChangesEnvironment=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── Files ──────────────────────────────────────────────────────────────────────

[Files]
; The compiled application (single executable)
Source: "..\dist\AI_Meetings.exe"; DestDir: "{app}"; Flags: ignoreversion

; FFmpeg — needed by Whisper at runtime
Source: "bundled\ffmpeg\ffmpeg.exe";  DestDir: "{app}"; Flags: ignoreversion
Source: "bundled\ffmpeg\ffprobe.exe"; DestDir: "{app}"; Flags: ignoreversion

; App icon (for shortcuts)
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userdesktop}\{#AppName}";         Filename: "{app}\AI_Meetings.exe"; IconFilename: "{app}\icon.ico"; Comment: "Launch AI Meetings"
Name: "{group}\{#AppName}";               Filename: "{app}\AI_Meetings.exe"; IconFilename: "{app}\icon.ico"
Name: "{group}\Uninstall {#AppName}";     Filename: "{uninstallexe}"

[Registry]
; Add {app} to user PATH so ffmpeg/ffprobe are found
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
  ValueData: "{olddata};{app}"; \
  Check: NeedsAddPath(ExpandConstant('{app}')); Flags: preservestringtype

[Run]
; Offer to launch after install
Filename: "{app}\AI_Meetings.exe"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent unchecked

; ── Pascal code ────────────────────────────────────────────────────────────────

[Code]

function ContainsPath(Existing, NewPath: String): Boolean;
begin
  Result := Pos(Lowercase(NewPath), Lowercase(Existing)) > 0;
end;

function NeedsAddPath(NewPath: String): Boolean;
var
  OldPath: String;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OldPath) then
    OldPath := '';
  Result := not ContainsPath(OldPath, NewPath);
end;

// ── Write empty .env template after install ───────────────────────────────────
// API настраивается в самом приложении через поле "API Base URL"

procedure WriteEnvFile;
var
  EnvPath, Content: String;
begin
  ForceDirectories(ExpandConstant('{localappdata}\AI Meetings'));
  EnvPath := ExpandConstant('{localappdata}\AI Meetings\.env');

  // Не перезаписываем если уже существует (повторная установка)
  if FileExists(EnvPath) then
    Exit;

  Content := '# AI Meetings configuration' + #13#10;
  Content := Content + '# Configure API via the app UI after launch' + #13#10 + #13#10;
  Content := Content + '# OpenAI cloud:' + #13#10;
  Content := Content + '# OPENAI_API_KEY=sk-proj-...' + #13#10 + #13#10;
  Content := Content + '# LM Studio (local):' + #13#10;
  Content := Content + '# OPENAI_API_BASE=http://127.0.0.1:1234/api/v1' + #13#10 + #13#10;
  Content := Content + '# CHATGPT_MODEL=' + #13#10;
  Content := Content + '# WHISPER_MODEL=base' + #13#10;
  Content := Content + '# WHISPER_LANGUAGE=ru' + #13#10;

  SaveStringToFile(EnvPath, Content, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteEnvFile;
end;
