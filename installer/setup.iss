; AI Meetings — InnoSetup 6 installer script
; Developer: Mikhail Depeshko
; Build: .\build_now.ps1  (from installer/ directory)
; Output: dist\AI_Meetings_Setup.exe

#define AppName      "AI Meetings"
#define AppVersion   "1.0"
#define AppPublisher "Mikhail Depeshko"
#define AppURL       "https://github.com/depeshko/ai-meetings"
#define AppCopyright "Copyright (C) 2026 Mikhail Depeshko"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppCopyright={#AppCopyright}
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
VersionInfoVersion=1.0.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoCopyright={#AppCopyright}
VersionInfoProductName={#AppName}
VersionInfoProductVersion=1.0.0.0

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── CustomMessages: ASCII only to avoid encoding issues ──────────────────────
[CustomMessages]
RunAppLabel=Launch AI Meetings now
russian.RunAppLabel=Launch AI Meetings now

; ── Files ──────────────────────────────────────────────────────────────────────

[Files]
; The compiled application (single executable)
Source: "..\dist\AI_Meetings.exe"; DestDir: "{app}"; Flags: ignoreversion

; FFmpeg — needed by Whisper at runtime
Source: "bundled\ffmpeg\ffmpeg.exe";  DestDir: "{app}"; Flags: ignoreversion
Source: "bundled\ffmpeg\ffprobe.exe"; DestDir: "{app}"; Flags: ignoreversion

; WhisperService — whisper.net with Vulkan GPU + CPU fallback backends
Source: "..\data\whisper_service\*"; DestDir: "{app}\whisper_service"; Flags: ignoreversion recursesubdirs

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
  Description: "{cm:RunAppLabel}"; \
  Flags: nowait postinstall skipifsilent unchecked

; ── Pascal code ────────────────────────────────────────────────────────────────

[Code]

var
  ModelPage: TInputOptionWizardPage;

// ── Whisper model selection ───────────────────────────────────────────────────

function GetSelectedModel: String;
begin
  case ModelPage.SelectedValueIndex of
    0: Result := 'tiny';
    1: Result := 'base';
    2: Result := 'small';
    3: Result := 'medium';
    4: Result := 'large-v3-turbo';
    5: Result := 'large-v3';
  else
    Result := 'base';
  end;
end;

procedure InitializeWizard;
begin
  ModelPage := CreateInputOptionPage(
    wpSelectProgramGroup,
    'Whisper Speech Recognition Model',
    'Choose which model to download on first launch',
    'The selected model is downloaded automatically when the app first starts.' + #13#10 +
    'Larger models are more accurate but require more disk space and time.',
    True,   { True = radio buttons (exclusive) }
    False   { False = list style }
  );
  ModelPage.Add('tiny           ~75 MB   | fast, lower accuracy');
  ModelPage.Add('base          ~142 MB   | good for short phrases  [recommended]');
  ModelPage.Add('small         ~466 MB   | good quality');
  ModelPage.Add('medium         ~1.5 GB  | high quality');
  ModelPage.Add('large-v3-turbo ~1.6 GB  | very high quality, faster than large');
  ModelPage.Add('large-v3       ~3.1 GB  | maximum quality');
  ModelPage.SelectedValueIndex := 1;  { default: base }
end;

// ── PATH helpers ──────────────────────────────────────────────────────────────

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

// ── Write .env template after install ────────────────────────────────────────

procedure WriteEnvFile;
var
  EnvPath, Content: String;
begin
  ForceDirectories(ExpandConstant('{localappdata}\AI Meetings'));
  EnvPath := ExpandConstant('{localappdata}\AI Meetings\.env');

  // Don't overwrite on reinstall — user settings (API keys etc.) are preserved.
  // To change the Whisper model after reinstall, use the app Settings panel.
  if FileExists(EnvPath) then
    Exit;

  Content := '# AI Meetings configuration' + #13#10;
  Content := Content + '# Developed by Mikhail Depeshko' + #13#10;
  Content := Content + '# Configure API via the app UI after launch' + #13#10 + #13#10;
  Content := Content + '# OpenAI cloud:' + #13#10;
  Content := Content + '# OPENAI_API_KEY=sk-proj-...' + #13#10 + #13#10;
  Content := Content + '# LM Studio (local):' + #13#10;
  Content := Content + '# OPENAI_API_BASE=http://127.0.0.1:1234/api/v1' + #13#10 + #13#10;
  Content := Content + '# CHATGPT_MODEL=' + #13#10;
  Content := Content + 'WHISPER_MODEL=' + GetSelectedModel + #13#10;
  Content := Content + '# WHISPER_LANGUAGE=ru' + #13#10;

  SaveStringToFile(EnvPath, Content, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteEnvFile;
end;

// ── Uninstall: remove {app} from user PATH ───────────────────────────────────

procedure RemoveFromPath(AppPath: String);
var
  OldPath, NewPath, Remaining, Part: String;
  SepPos: Integer;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OldPath) then
    Exit;

  Remaining := OldPath;
  NewPath := '';
  repeat
    SepPos := Pos(';', Remaining);
    if SepPos > 0 then
    begin
      Part := Copy(Remaining, 1, SepPos - 1);
      Remaining := Copy(Remaining, SepPos + 1, Length(Remaining));
    end
    else
    begin
      Part := Remaining;
      Remaining := '';
    end;

    while (Length(Part) > 0) and (Part[1] = ' ') do
      Part := Copy(Part, 2, Length(Part));
    while (Length(Part) > 0) and (Part[Length(Part)] = ' ') do
      Part := Copy(Part, 1, Length(Part) - 1);

    if (Part <> '') and (Lowercase(Part) <> Lowercase(AppPath)) then
    begin
      if NewPath <> '' then
        NewPath := NewPath + ';';
      NewPath := NewPath + Part;
    end;
  until Remaining = '';

  RegWriteExpandStringValue(HKCU, 'Environment', 'Path', NewPath);
end;

// ── Uninstall: offer to remove user data ─────────────────────────────────────

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir, Msg: String;
begin
  if CurUninstallStep = usUninstall then
    RemoveFromPath(ExpandConstant('{app}'));

  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\AI Meetings');
    if DirExists(DataDir) then
    begin
      Msg := 'Remove user data (Whisper models, settings, .env)?' + #13#10 +
             DataDir + #13#10#13#10 +
             'Models can be re-downloaded on next launch.';
      if MsgBox(Msg, mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;

// ── Ready memo ───────────────────────────────────────────────────────────────

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine +
            MemoGroupInfo + NewLine + NewLine +
            'Developer: Mikhail Depeshko' + NewLine +
            'Version: {#AppVersion}' + NewLine +
            'Whisper model: ' + GetSelectedModel +
            ' (downloaded on first launch)';
end;
