# ============================================================
#  AI Meetings — Build Windows Installer (.exe)
#  Requirements: InnoSetup 6 (iscc.exe in PATH or default location)
#  Usage: .\build_installer.ps1
#         .\build_installer.ps1 -SkipFfmpeg
#         .\build_installer.ps1 -Version "1.1"
# ============================================================

param(
    [string]$Version    = "1.0",
    [switch]$SkipFfmpeg = $false,
    [switch]$SkipAssets = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent $ScriptDir
$BundledDir = Join-Path $ScriptDir "bundled\ffmpeg"
$AssetsDir  = Join-Path $ScriptDir "assets"
$DistDir    = Join-Path $RepoRoot "dist"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AI Meetings — Installer Builder" -ForegroundColor Cyan
Write-Host "  Version: $Version" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Find InnoSetup ────────────────────────────────────────────────────────

$IsccPaths = @(
    "iscc",   # if in PATH
    "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

$IsccExe = $null
foreach ($p in $IsccPaths) {
    if (Get-Command $p -ErrorAction SilentlyContinue) {
        $IsccExe = $p
        break
    }
}

if (-not $IsccExe) {
    Write-Host "ERROR: InnoSetup 6 (iscc.exe) not found." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install InnoSetup 6 from: https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
    Write-Host "Or via winget:" -ForegroundColor Yellow
    Write-Host "  winget install JRSoftware.InnoSetup" -ForegroundColor White
    Write-Host ""
    exit 1
}

Write-Host "[1/5] InnoSetup found: $IsccExe" -ForegroundColor Green

# ── 2. Check project files ───────────────────────────────────────────────────

$RequiredFiles = @(
    (Join-Path $RepoRoot "main.py"),
    (Join-Path $RepoRoot "requirements.txt"),
    (Join-Path $RepoRoot "src"),
    (Join-Path $RepoRoot "utils")
)

foreach ($f in $RequiredFiles) {
    if (-not (Test-Path $f)) {
        Write-Host "ERROR: Required file/dir not found: $f" -ForegroundColor Red
        exit 1
    }
}

Write-Host "[2/5] Project files OK" -ForegroundColor Green

# ── 3. Download FFmpeg (if needed) ───────────────────────────────────────────

$FfmpegExe  = Join-Path $BundledDir "ffmpeg.exe"
$FfprobeExe = Join-Path $BundledDir "ffprobe.exe"

if ($SkipFfmpeg) {
    Write-Host "[3/5] FFmpeg: SKIPPED (--SkipFfmpeg)" -ForegroundColor Yellow
} elseif ((Test-Path $FfmpegExe) -and (Test-Path $FfprobeExe)) {
    $Size = [math]::Round((Get-Item $FfmpegExe).Length / 1MB, 1)
    Write-Host "[3/5] FFmpeg already bundled (ffmpeg.exe = ${Size} MB)" -ForegroundColor Green
} else {
    Write-Host "[3/5] Downloading FFmpeg essentials build..." -ForegroundColor Yellow

    # BtbN/FFmpeg-Builds — latest Windows essentials (x64, gpl-shared)
    $FfmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    $ZipPath   = Join-Path $env:TEMP "ffmpeg_download.zip"
    $ExtractTo = Join-Path $env:TEMP "ffmpeg_extract"

    try {
        Write-Host "  Downloading from: $FfmpegUrl"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $FfmpegUrl -OutFile $ZipPath -UseBasicParsing

        Write-Host "  Extracting..."
        if (Test-Path $ExtractTo) { Remove-Item $ExtractTo -Recurse -Force }
        Expand-Archive -Path $ZipPath -DestinationPath $ExtractTo

        # Find ffmpeg.exe inside extracted zip (nested folder)
        $FfmpegBin = Get-ChildItem -Path $ExtractTo -Recurse -Filter "ffmpeg.exe" |
                     Where-Object { $_.DirectoryName -match "\\bin$" } |
                     Select-Object -First 1

        if (-not $FfmpegBin) {
            # Fallback: any ffmpeg.exe in bin/
            $FfmpegBin = Get-ChildItem -Path $ExtractTo -Recurse -Filter "ffmpeg.exe" |
                         Select-Object -First 1
        }

        if (-not $FfmpegBin) {
            throw "ffmpeg.exe not found in downloaded archive"
        }

        $BinDir = $FfmpegBin.DirectoryName

        # Create bundled dir
        New-Item -ItemType Directory -Force -Path $BundledDir | Out-Null

        Copy-Item (Join-Path $BinDir "ffmpeg.exe")  $FfmpegExe  -Force
        Copy-Item (Join-Path $BinDir "ffprobe.exe") $FfprobeExe -Force

        # Cleanup
        Remove-Item $ZipPath    -Force -ErrorAction SilentlyContinue
        Remove-Item $ExtractTo  -Recurse -Force -ErrorAction SilentlyContinue

        $SizeMB = [math]::Round((Get-Item $FfmpegExe).Length / 1MB, 1)
        Write-Host "  FFmpeg bundled successfully (${SizeMB} MB)" -ForegroundColor Green

    } catch {
        Write-Host "  WARNING: Failed to download FFmpeg: $_" -ForegroundColor Yellow
        Write-Host "  Installer will be built WITHOUT bundled FFmpeg." -ForegroundColor Yellow
        Write-Host "  Users will need to install FFmpeg manually." -ForegroundColor Yellow

        # Remove ffmpeg section from setup.iss temporarily — or just warn
        # For now just continue without it
    }
}

# ── 4. Create placeholder assets (icon etc.) ─────────────────────────────────

New-Item -ItemType Directory -Force -Path $AssetsDir | Out-Null

if (-not $SkipAssets) {
    # Generate minimal valid ICO file if none exists
    $IconPath = Join-Path $AssetsDir "icon.ico"
    if (-not (Test-Path $IconPath)) {
        Write-Host "[4/5] Creating placeholder icon..." -ForegroundColor Yellow
        # Copy Windows default app icon as placeholder
        $WinIcon = "$env:SystemRoot\System32\shell32.dll"
        # Extract icon via PowerShell — use a simple approach: copy from system
        # Just create a minimal placeholder note
        $PlaceholderNote = Join-Path $AssetsDir "REPLACE_ICONS.txt"
        Set-Content $PlaceholderNote @"
Place your icon files here:
  icon.ico      — main application icon (256x256 recommended)
  wizard.bmp    — InnoSetup wizard image (164x314 pixels)
  icon_small.bmp — InnoSetup small image (55x58 pixels)

To generate from a PNG:
  Use GIMP, Photoshop, or online converter (e.g. icoconvert.com)

The installer will use a default Windows icon if these are missing.
"@
        Write-Host "  Placeholder note created. Replace with real icons before release." -ForegroundColor Yellow

        # Use a Windows system ICO as default placeholder
        try {
            Add-Type -AssemblyName System.Drawing
            $icon = [System.Drawing.Icon]::ExtractAssociatedIcon("$env:SystemRoot\System32\notepad.exe")
            $fileStream = [System.IO.FileStream]::new($IconPath, [System.IO.FileMode]::Create)
            $icon.Save($fileStream)
            $fileStream.Close()
            Write-Host "  Default icon created from notepad.exe" -ForegroundColor Green
        } catch {
            Write-Host "  Could not create icon: $_" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[4/5] Icon found: $IconPath" -ForegroundColor Green
    }

    # Create minimal BMP placeholders for wizard images
    $WizardBmp = Join-Path $AssetsDir "wizard.bmp"
    $SmallBmp  = Join-Path $AssetsDir "icon_small.bmp"

    foreach ($bmp in @($WizardBmp, $SmallBmp)) {
        if (-not (Test-Path $bmp)) {
            try {
                $w = if ($bmp -eq $WizardBmp) { 164 } else { 55 }
                $h = if ($bmp -eq $WizardBmp) { 314 } else { 58 }
                Add-Type -AssemblyName System.Drawing
                $bitmap = [System.Drawing.Bitmap]::new($w, $h)
                $g = [System.Drawing.Graphics]::FromImage($bitmap)
                $g.Clear([System.Drawing.Color]::FromArgb(30, 100, 200))
                $g.Dispose()
                $bitmap.Save($bmp, [System.Drawing.Imaging.ImageFormat]::Bmp)
                $bitmap.Dispose()
            } catch {
                # Non-critical
            }
        }
    }
} else {
    Write-Host "[4/5] Assets: SKIPPED" -ForegroundColor Yellow
}

# ── 5. Patch version in setup.iss & build ────────────────────────────────────

$IssFile = Join-Path $ScriptDir "setup.iss"
$IssTmp  = Join-Path $env:TEMP "setup_build.iss"

# Read and patch version
$IssContent = Get-Content $IssFile -Raw
$IssContent = $IssContent -replace '#define AppVersion\s+"[^"]+"', "#define AppVersion   `"$Version`""

# If FFmpeg wasn't downloaded, comment out FFmpeg lines to avoid build error
if (-not (Test-Path $FfmpegExe)) {
    $IssContent = $IssContent -replace `
        '(Source: "bundled\\ffmpeg\\[^"]+";[^\n]+\n)', `
        '; [FFMPEG NOT BUNDLED] $1'
}

Set-Content -Path $IssTmp -Value $IssContent -Encoding UTF8

Write-Host "[5/5] Building installer..." -ForegroundColor Yellow

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

# Run ISCC
$BuildArgs = "`"$IssTmp`""
$proc = Start-Process -FilePath $IsccExe -ArgumentList $BuildArgs `
    -WorkingDirectory $ScriptDir -Wait -PassThru -NoNewWindow

if ($proc.ExitCode -ne 0) {
    Write-Host ""
    Write-Host "ERROR: InnoSetup build failed (exit code $($proc.ExitCode))" -ForegroundColor Red
    exit 1
}

# ── Done ─────────────────────────────────────────────────────────────────────

$OutputExe = Join-Path $DistDir "AI_Meetings_Setup.exe"
if (Test-Path $OutputExe) {
    $SizeMB = [math]::Round((Get-Item $OutputExe).Length / 1MB, 1)
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  BUILD SUCCESSFUL!" -ForegroundColor Green
    Write-Host "  Output: $OutputExe" -ForegroundColor Green
    Write-Host "  Size:   ${SizeMB} MB" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "WARNING: Expected output not found: $OutputExe" -ForegroundColor Yellow
}
