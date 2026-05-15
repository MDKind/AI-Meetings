# Build script for AI Meetings installer
# Prerequisite: dist\AI_Meetings.exe must already exist
# Usage: .\build_now.ps1  (double-click or run from PowerShell)
Set-Location $PSScriptRoot
$ErrorActionPreference = "Stop"

$IsccLocal = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
$IsccGlobal = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if (Test-Path $IsccLocal) {
    $IsccExe = $IsccLocal
} elseif (Test-Path $IsccGlobal) {
    $IsccExe = $IsccGlobal
} else {
    Write-Host "ERROR: Inno Setup 6 (ISCC.exe) not found." -ForegroundColor Red
    exit 1
}

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$AssetsDir  = Join-Path $PSScriptRoot "assets"
$BundledDir = Join-Path $PSScriptRoot "bundled\ffmpeg"
$DistDir    = Join-Path $RepoRoot "dist"
$AppExe     = Join-Path $DistDir "AI_Meetings.exe"

Write-Host "AI Meetings - Building Setup Installer" -ForegroundColor Cyan

# [1] Check compiled app
if (-not (Test-Path $AppExe)) {
    Write-Host "ERROR: dist\AI_Meetings.exe not found." -ForegroundColor Red
    Write-Host "Build it first:" -ForegroundColor Yellow
    Write-Host "  build_venv\Scripts\python.exe -m PyInstaller AI_Meetings.spec --clean" -ForegroundColor White
    exit 1
}
$szApp = [math]::Round((Get-Item $AppExe).Length / 1MB, 0)
Write-Host "[1/4] AI_Meetings.exe found ($szApp MB)" -ForegroundColor Green

# [2] Assets
New-Item -ItemType Directory -Force -Path $AssetsDir | Out-Null

$IconPath = Join-Path $AssetsDir "icon.ico"
if (-not (Test-Path $IconPath)) {
    Write-Host "[2/4] Creating placeholder icon..." -ForegroundColor Yellow
    try {
        Add-Type -AssemblyName System.Drawing
        $icon = [System.Drawing.Icon]::ExtractAssociatedIcon("$env:SystemRoot\System32\notepad.exe")
        $fs = [System.IO.FileStream]::new($IconPath, [System.IO.FileMode]::Create)
        $icon.Save($fs); $fs.Close()
    } catch { Write-Host "     icon creation failed (non-critical)" }
}

foreach ($bmp in @(@{f="wizard.bmp";w=164;h=314}, @{f="icon_small.bmp";w=55;h=58})) {
    $p = Join-Path $AssetsDir $bmp.f
    if (-not (Test-Path $p)) {
        try {
            Add-Type -AssemblyName System.Drawing
            $b = [System.Drawing.Bitmap]::new($bmp.w, $bmp.h)
            $g = [System.Drawing.Graphics]::FromImage($b)
            $g.Clear([System.Drawing.Color]::FromArgb(30, 90, 180)); $g.Dispose()
            $b.Save($p, [System.Drawing.Imaging.ImageFormat]::Bmp); $b.Dispose()
        } catch {}
    }
}
Write-Host "[2/4] Assets OK" -ForegroundColor Green

# [3] FFmpeg
New-Item -ItemType Directory -Force -Path $BundledDir | Out-Null
$FfmpegExe  = Join-Path $BundledDir "ffmpeg.exe"
$FfprobeExe = Join-Path $BundledDir "ffprobe.exe"

if (-not ((Test-Path $FfmpegExe) -and (Test-Path $FfprobeExe))) {
    Write-Host "[3/4] Downloading FFmpeg..." -ForegroundColor Yellow
    $ZipUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    $ZipTmp = Join-Path $env:TEMP "ffmpeg_dl.zip"
    $ExtTmp = Join-Path $env:TEMP "ffmpeg_ex"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipTmp -UseBasicParsing
        if (Test-Path $ExtTmp) { Remove-Item $ExtTmp -Recurse -Force }
        Expand-Archive -Path $ZipTmp -DestinationPath $ExtTmp
        $BinDir = (Get-ChildItem -Path $ExtTmp -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1).DirectoryName
        Copy-Item (Join-Path $BinDir "ffmpeg.exe")  $FfmpegExe  -Force
        Copy-Item (Join-Path $BinDir "ffprobe.exe") $FfprobeExe -Force
        Remove-Item $ZipTmp, $ExtTmp -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "     FFmpeg OK" -ForegroundColor Green
    } catch {
        Write-Host "     WARNING: FFmpeg download failed: $_" -ForegroundColor Yellow
    }
} else {
    $sz = [math]::Round((Get-Item $FfmpegExe).Length / 1MB, 0)
    Write-Host "[3/4] FFmpeg bundled ($sz MB)" -ForegroundColor Green
}

# LICENSE
$LicFile = Join-Path $RepoRoot "LICENSE.txt"
if (-not (Test-Path $LicFile)) {
    Set-Content $LicFile "MIT License`r`nCopyright (c) 2025 AI Meetings"
}

# [4] Patch .iss and build
Write-Host "[4/4] Compiling installer..." -ForegroundColor Yellow
$IssFile    = Join-Path $PSScriptRoot "setup.iss"
$IssTmp     = Join-Path $env:TEMP "ai_meetings_setup.iss"
$IssContent = Get-Content $IssFile -Raw

# Use .Replace() (literal, not regex) to avoid backslash escaping issues
$IssContent = $IssContent.Replace('OutputDir=..\dist',            "OutputDir=$DistDir")
$IssContent = $IssContent.Replace('LicenseFile=..\LICENSE.txt',   "LicenseFile=$RepoRoot\LICENSE.txt")
$IssContent = $IssContent.Replace('SetupIconFile=assets\',        "SetupIconFile=$PSScriptRoot\assets\")
$IssContent = $IssContent.Replace('WizardImageFile=assets\',      "WizardImageFile=$PSScriptRoot\assets\")
$IssContent = $IssContent.Replace('WizardSmallImageFile=assets\', "WizardSmallImageFile=$PSScriptRoot\assets\")
$IssContent = $IssContent.Replace('Source: "..\dist\',            "Source: `"$DistDir\")
$IssContent = $IssContent.Replace('Source: "..\data\',            "Source: `"$RepoRoot\data\")
$IssContent = $IssContent.Replace('Source: "bundled\',            "Source: `"$PSScriptRoot\bundled\")
$IssContent = $IssContent.Replace('Source: "assets\',             "Source: `"$PSScriptRoot\assets\")

Set-Content -Path $IssTmp -Value $IssContent -Encoding Default

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

# Run ISCC directly (& operator captures output to console)
& $IsccExe $IssTmp
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: InnoSetup build failed (exit $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

$OutExe = Join-Path $DistDir "AI_Meetings_Setup.exe"
if (Test-Path $OutExe) {
    $sz = [math]::Round((Get-Item $OutExe).Length / 1MB, 0)
    Write-Host ""
    Write-Host "SUCCESS: $OutExe ($sz MB)" -ForegroundColor Green
}
