; AI Meetings — InnoSetup 6 installer script
; Build: iscc.exe setup.iss  (from installer/ directory)
; Output: dist\AI_Meetings_Setup.exe

#define AppName      "AI Meetings"
#define AppVersion   "1.0"
#define AppPublisher "AI Meetings"
#define AppExeName   "launch.bat"
#define MinPython    "3.8"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com
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
; 64-bit only (Python, FFmpeg, PyTorch all 64-bit)
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\assets\icon.ico
UninstallDisplayName={#AppName}
; Splash / wizard images
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
; Project source
Source: "..\src\*";      DestDir: "{app}\src";      Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\utils\*";    DestDir: "{app}\utils";    Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\data\*";     DestDir: "{app}\data";     Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\docs\*";     DestDir: "{app}\docs";     Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\scripts\*";  DestDir: "{app}\scripts";  Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\tools\*";    DestDir: "{app}\tools";    Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\main.py";            DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt";   DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\minimal_install.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE.txt";        DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Installer helper scripts
Source: "scripts\install_deps.bat"; DestDir: "{app}"; Flags: ignoreversion

; Assets (icon for shortcut)
Source: "assets\icon.ico";         DestDir: "{app}\assets"; Flags: ignoreversion

; FFmpeg bundled binaries
Source: "bundled\ffmpeg\ffmpeg.exe";  DestDir: "{app}\ffmpeg"; Flags: ignoreversion
Source: "bundled\ffmpeg\ffprobe.exe"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion

; ── Shortcuts ──────────────────────────────────────────────────────────────────

[Icons]
; Desktop shortcut → launch.bat (created by installer code)
Name: "{userdesktop}\{#AppName}";    Filename: "{app}\launch.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; Comment: "Запустить AI Meetings"
; Start menu
Name: "{group}\{#AppName}";          Filename: "{app}\launch.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Удалить {#AppName}";  Filename: "{uninstallexe}"

; ── Registry ───────────────────────────────────────────────────────────────────

[Registry]
; Add {app}\ffmpeg to user PATH (so Whisper finds ffmpeg)
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
  ValueData: "{olddata};{app}\ffmpeg"; \
  Check: NeedsAddPath('{app}\ffmpeg'); Flags: preservestringtype

; ── Run after install ──────────────────────────────────────────────────────────

[Run]
; Install Python packages — shown in progress window
Filename: "{app}\install_deps.bat"; \
  Description: "Установка Python-зависимостей (может занять 5–15 минут)"; \
  StatusMsg: "Устанавливаем зависимости Python..."; \
  Flags: waituntilterminated shellexec runasoriginaluser

; Offer to launch app after install
Filename: "{app}\launch.bat"; \
  Description: "Запустить {#AppName} сейчас"; \
  Flags: nowait postinstall skipifsilent unchecked shellexec

; ── Pascal code ────────────────────────────────────────────────────────────────

[Code]

// ── Constants & Globals ──────────────────────────────────────────────────────

var
  // API config page
  ApiPage:      TWizardPage;
  ApiKeyEdit:   TPasswordEdit;
  ApiBaseEdit:  TEdit;
  ApiLabelKey:  TLabel;
  ApiLabelBase: TLabel;
  ApiNote:      TLabel;

  // Python check result
  PythonExe: String;
  PythonOK:  Boolean;


// ── Helpers ──────────────────────────────────────────────────────────────────

// Run a command, return exit code
function ExecAndGetCode(Cmd, Args, WorkDir: String): Integer;
var
  Code: Integer;
begin
  if not Exec(Cmd, Args, WorkDir, SW_HIDE, ewWaitUntilTerminated, Code) then
    Code := -1;
  Result := Code;
end;

// Check if a string S is already present in PATH-style value
function ContainsPath(Existing, NewPath: String): Boolean;
var
  P: Integer;
begin
  NewPath := Lowercase(NewPath);
  Existing := Lowercase(Existing);
  P := Pos(NewPath, Existing);
  Result := (P > 0);
end;

// Used in [Registry] Check= to skip if path already present
function NeedsAddPath(NewPath: String): Boolean;
var
  OldPath: String;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OldPath) then
    OldPath := '';
  Result := not ContainsPath(OldPath, NewPath);
end;

// Find python.exe in PATH / registry, return version string or ''
function FindPython(var ExePath: String): String;
var
  TmpFile, Ver: String;
  Code: Integer;
begin
  TmpFile := ExpandConstant('{tmp}\pyver.txt');

  // Try `python --version` first
  if Exec('cmd.exe',
          '/c python --version > "' + TmpFile + '" 2>&1',
          '', SW_HIDE, ewWaitUntilTerminated, Code) then
  begin
    if LoadStringFromFile(TmpFile, Ver) then
    begin
      Ver := Trim(Ver);
      if Pos('Python 3.', Ver) = 1 then
      begin
        ExePath := 'python';
        Result  := Ver;
        Exit;
      end;
    end;
  end;

  // Try py launcher
  if Exec('cmd.exe',
          '/c py -3 --version > "' + TmpFile + '" 2>&1',
          '', SW_HIDE, ewWaitUntilTerminated, Code) then
  begin
    if LoadStringFromFile(TmpFile, Ver) then
    begin
      Ver := Trim(Ver);
      if Pos('Python 3.', Ver) = 1 then
      begin
        ExePath := 'py -3';
        Result  := Ver;
        Exit;
      end;
    end;
  end;

  ExePath := '';
  Result  := '';
end;

// Check Python version is >= MinPython (3.8)
function PythonVersionOK(VerStr: String): Boolean;
var
  Parts: TStringList;
  Major, Minor: Integer;
  Core: String;
begin
  // VerStr like "Python 3.11.9"
  Result := False;
  Core := VerStr;
  // Strip "Python " prefix
  if Pos('Python ', Core) = 1 then
    Delete(Core, 1, 7);
  Parts := TStringList.Create;
  try
    Parts.Delimiter := '.';
    Parts.DelimitedText := Core;
    if Parts.Count >= 2 then
    begin
      Major := StrToIntDef(Parts[0], 0);
      Minor := StrToIntDef(Parts[1], 0);
      Result := (Major > 3) or ((Major = 3) and (Minor >= 8));
    end;
  finally
    Parts.Free;
  end;
end;


// ── Wizard Init ──────────────────────────────────────────────────────────────

procedure InitializeWizard;
var
  VerStr: String;
begin
  // ── Check Python ──────────────────────────────────────────────────────────
  PythonOK := False;
  VerStr := FindPython(PythonExe);
  if (VerStr <> '') and PythonVersionOK(VerStr) then
    PythonOK := True;

  // ── API Key page ──────────────────────────────────────────────────────────
  ApiPage := CreateCustomPage(
    wpSelectDir,
    'Настройка API',
    'Введите ключ OpenAI API (или оставьте поле пустым для локальных моделей LM Studio/Ollama)'
  );

  ApiLabelKey := TLabel.Create(ApiPage);
  ApiLabelKey.Parent  := ApiPage.Surface;
  ApiLabelKey.Caption := 'OpenAI API Key:';
  ApiLabelKey.Top     := 8;
  ApiLabelKey.Left    := 0;
  ApiLabelKey.Width   := ApiPage.SurfaceWidth;

  ApiKeyEdit := TPasswordEdit.Create(ApiPage);
  ApiKeyEdit.Parent := ApiPage.Surface;
  ApiKeyEdit.Top    := ApiLabelKey.Top + ApiLabelKey.Height + 4;
  ApiKeyEdit.Left   := 0;
  ApiKeyEdit.Width  := ApiPage.SurfaceWidth;
  ApiKeyEdit.Text   := '';

  ApiLabelBase := TLabel.Create(ApiPage);
  ApiLabelBase.Parent  := ApiPage.Surface;
  ApiLabelBase.Caption := 'API Base URL (необязательно, для LM Studio / Ollama):';
  ApiLabelBase.Top     := ApiKeyEdit.Top + ApiKeyEdit.Height + 16;
  ApiLabelBase.Left    := 0;
  ApiLabelBase.Width   := ApiPage.SurfaceWidth;

  ApiBaseEdit := TEdit.Create(ApiPage);
  ApiBaseEdit.Parent := ApiPage.Surface;
  ApiBaseEdit.Top    := ApiLabelBase.Top + ApiLabelBase.Height + 4;
  ApiBaseEdit.Left   := 0;
  ApiBaseEdit.Width  := ApiPage.SurfaceWidth;
  ApiBaseEdit.Text   := '';

  ApiNote := TLabel.Create(ApiPage);
  ApiNote.Parent    := ApiPage.Surface;
  ApiNote.Caption   :=
    'Примеры Base URL:' + #13#10 +
    '  LM Studio:  http://127.0.0.1:1234/v1' + #13#10 +
    '  Ollama:     http://127.0.0.1:11434/v1' + #13#10 +
    #13#10 +
    'Получить ключ OpenAI: https://platform.openai.com/api-keys';
  ApiNote.Top       := ApiBaseEdit.Top + ApiBaseEdit.Height + 12;
  ApiNote.Left      := 0;
  ApiNote.Width     := ApiPage.SurfaceWidth;
  ApiNote.Height    := 80;
  ApiNote.WordWrap  := True;
end;


// ── Page helpers ─────────────────────────────────────────────────────────────

// Warn about missing Python before installation starts
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Msg: String;
begin
  Result := True;

  if CurPageID = wpWelcome then
  begin
    if not PythonOK then
    begin
      Msg :=
        'Python 3.8 или выше не найден на этом компьютере.' + #13#10 +
        #13#10 +
        'Для работы AI Meetings требуется Python.' + #13#10 +
        'Пожалуйста, установите Python с сайта python.org перед продолжением.' + #13#10 +
        #13#10 +
        'Важно: при установке Python обязательно отметьте опцию' + #13#10 +
        '"Add Python to PATH".' + #13#10 +
        #13#10 +
        'Открыть страницу загрузки Python сейчас?';

      if MsgBox(Msg, mbConfirmation, MB_YESNO) = IDYES then
        ShellExec('open', 'https://www.python.org/downloads/', '', '', SW_SHOW, ewNoWait, 0);

      Result := False; // Block until Python installed
    end;
  end;
end;

// Show detected Python version on Welcome page
procedure CurPageChanged(CurPageID: Integer);
var
  VerStr: String;
begin
  if CurPageID = wpWelcome then
  begin
    VerStr := FindPython(PythonExe);
    if (VerStr <> '') and PythonVersionOK(VerStr) then
    begin
      // Update subtitle dynamically — not easy in InnoSetup, use balloon
    end;
  end;
end;


// ── Post-install: write .env ─────────────────────────────────────────────────

procedure WriteEnvFile;
var
  ApiKey, ApiBase, EnvPath, Content: String;
begin
  ApiKey  := Trim(ApiKeyEdit.Text);
  ApiBase := Trim(ApiBaseEdit.Text);
  EnvPath := ExpandConstant('{app}\.env');

  Content := '# AI Meetings — environment configuration' + #13#10;
  Content := Content + '# Generated by installer on ' + GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + #13#10;
  Content := Content + #13#10;

  if ApiKey <> '' then
    Content := Content + 'OPENAI_API_KEY=' + ApiKey + #13#10
  else
    Content := Content + '# OPENAI_API_KEY=your_key_here' + #13#10;

  if ApiBase <> '' then
    Content := Content + 'OPENAI_API_BASE=' + ApiBase + #13#10
  else
    Content := Content + '# OPENAI_API_BASE=' + #13#10;

  Content := Content + #13#10;
  Content := Content + '# Optional settings' + #13#10;
  Content := Content + '# CHATGPT_MODEL=gpt-4o' + #13#10;
  Content := Content + '# WHISPER_MODEL=base' + #13#10;
  Content := Content + '# WHISPER_LANGUAGE=ru' + #13#10;

  if not SaveStringToFile(EnvPath, Content, False) then
    MsgBox('Не удалось создать файл .env.' + #13#10 +
           'Создайте его вручную в папке: ' + ExpandConstant('{app}'),
           mbError, MB_OK);
end;

// Write launch.bat (uses pythonw to hide console)
procedure WriteLaunchBat;
var
  BatPath, Launcher: String;
begin
  BatPath := ExpandConstant('{app}\launch.bat');
  Launcher :=
    '@echo off' + #13#10 +
    'cd /d "%~dp0"' + #13#10 +
    'set "PATH=%~dp0ffmpeg;%PATH%"' + #13#10 +
    #13#10 +
    ':: Check Python' + #13#10 +
    'python --version >nul 2>&1' + #13#10 +
    'if %errorlevel% neq 0 (' + #13#10 +
    '    echo Python not found. Please install Python 3.8+ from python.org' + #13#10 +
    '    pause' + #13#10 +
    '    exit /b 1' + #13#10 +
    ')' + #13#10 +
    #13#10 +
    'start "" pythonw.exe main.py' + #13#10;

  SaveStringToFile(BatPath, Launcher, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WriteEnvFile;
    WriteLaunchBat;
  end;
end;
