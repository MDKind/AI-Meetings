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

// ── API Key config page ───────────────────────────────────────────────────────

var
  ApiPage:      TWizardPage;
  ApiKeyEdit:   TPasswordEdit;
  ApiBaseEdit:  TEdit;
  ApiNote:      TLabel;

procedure InitializeWizard;
var
  LabelKey, LabelBase: TLabel;
begin
  ApiPage := CreateCustomPage(
    wpSelectDir,
    'API Configuration',
    'Enter your OpenAI API key (or leave blank for local models: LM Studio / Ollama)'
  );

  LabelKey := TLabel.Create(ApiPage);
  LabelKey.Parent  := ApiPage.Surface;
  LabelKey.Caption := 'OpenAI API Key:';
  LabelKey.Top     := 8;
  LabelKey.Left    := 0;
  LabelKey.Width   := ApiPage.SurfaceWidth;

  ApiKeyEdit := TPasswordEdit.Create(ApiPage);
  ApiKeyEdit.Parent := ApiPage.Surface;
  ApiKeyEdit.Top    := LabelKey.Top + LabelKey.Height + 4;
  ApiKeyEdit.Left   := 0;
  ApiKeyEdit.Width  := ApiPage.SurfaceWidth;

  LabelBase := TLabel.Create(ApiPage);
  LabelBase.Parent  := ApiPage.Surface;
  LabelBase.Caption := 'API Base URL (optional, for LM Studio / Ollama):';
  LabelBase.Top     := ApiKeyEdit.Top + ApiKeyEdit.Height + 16;
  LabelBase.Left    := 0;
  LabelBase.Width   := ApiPage.SurfaceWidth;

  ApiBaseEdit := TEdit.Create(ApiPage);
  ApiBaseEdit.Parent := ApiPage.Surface;
  ApiBaseEdit.Top    := LabelBase.Top + LabelBase.Height + 4;
  ApiBaseEdit.Left   := 0;
  ApiBaseEdit.Width  := ApiPage.SurfaceWidth;
  ApiBaseEdit.Text   := '';

  ApiNote := TLabel.Create(ApiPage);
  ApiNote.Parent   := ApiPage.Surface;
  ApiNote.Caption  :=
    'Base URL examples:' + #13#10 +
    '  LM Studio:  http://127.0.0.1:1234/v1' + #13#10 +
    '  Ollama:     http://127.0.0.1:11434/v1' + #13#10 +
    'Get OpenAI key: https://platform.openai.com/api-keys';
  ApiNote.Top      := ApiBaseEdit.Top + ApiBaseEdit.Height + 12;
  ApiNote.Left     := 0;
  ApiNote.Width    := ApiPage.SurfaceWidth;
  ApiNote.Height   := 70;
  ApiNote.WordWrap := True;
end;

// ── Write .env after install ──────────────────────────────────────────────────

procedure WriteEnvFile;
var
  ApiKey, ApiBase, EnvPath, Content: String;
begin
  ApiKey  := Trim(ApiKeyEdit.Text);
  ApiBase := Trim(ApiBaseEdit.Text);
  EnvPath := ExpandConstant('{app}\.env');

  Content := '# AI Meetings configuration' + #13#10;
  Content := Content + '# Generated by installer' + #13#10 + #13#10;

  if ApiKey <> '' then
    Content := Content + 'OPENAI_API_KEY=' + ApiKey + #13#10
  else
    Content := Content + '# OPENAI_API_KEY=your_key_here' + #13#10;

  if ApiBase <> '' then
    Content := Content + 'OPENAI_API_BASE=' + ApiBase + #13#10
  else
    Content := Content + '# OPENAI_API_BASE=' + #13#10;

  Content := Content + #13#10;
  Content := Content + '# CHATGPT_MODEL=gpt-4o' + #13#10;
  Content := Content + '# WHISPER_MODEL=base' + #13#10;
  Content := Content + '# WHISPER_LANGUAGE=ru' + #13#10;

  SaveStringToFile(EnvPath, Content, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteEnvFile;
end;
