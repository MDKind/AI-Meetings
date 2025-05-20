@echo off
echo ==============================================
echo    AI MEETINGS - Installation Script
echo ==============================================
echo.

:: Check Python
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python and add it to PATH.
    pause
    exit /b 1
)

:: Get Python version for correct wheel file
for /f "tokens=2" %%I in ('python --version 2^>^&1') do set PYTHON_VERSION=%%I
for /f "tokens=1,2 delims=." %%A in ("%PYTHON_VERSION%") do (
    set PYTHON_MAJOR=%%A
    set PYTHON_MINOR=%%B
)
echo [INFO] Detected Python: %PYTHON_VERSION% (Major: %PYTHON_MAJOR%, Minor: %PYTHON_MINOR%)

echo [INFO] Updating pip and build tools...
python -m pip install --upgrade pip
pip install --upgrade setuptools wheel
echo.

echo [INFO] Installing core dependencies...
echo [INFO] Installing numpy...
pip install numpy
echo.

echo [INFO] Installing audio processing libraries...
pip install pydub scipy
echo.

echo [INFO] Installing basic libraries...
pip install openai python-dotenv
echo.

echo [INFO] Installing PyTorch...
pip install torch
echo.

echo [INFO] Installing Whisper (via GitHub)...
pip install git+https://github.com/openai/whisper.git
if %errorlevel% neq 0 (
    echo [WARNING] Failed to install Whisper via GitHub.
    echo [INFO] Trying alternative method...
    pip install --upgrade setuptools
    pip install openai-whisper
)
echo.

echo [INFO] Installing sounddevice for audio capture...
pip install sounddevice
echo.

echo [INFO] Checking for FFmpeg...
where ffmpeg > nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg not found in PATH. Whisper works best with FFmpeg installed.
    echo [INFO] You have two options:
    echo   1. Install FFmpeg manually (recommended):
    echo      - Download from https://ffmpeg.org/download.html
    echo      - Add the bin directory to your PATH
    echo   2. Continue without FFmpeg (some features may not work optimally)
    
    choice /C YN /M "Do you want to continue without installing FFmpeg"
    if %errorlevel% equ 2 (
        echo.
        echo [INFO] Please install FFmpeg, then run this script again.
        echo       1. Download from https://ffmpeg.org/download.html
        echo       2. Extract the archive
        echo       3. Add the bin directory to your PATH
        echo.
        pause
        exit /b 1
    )
) else (
    echo [INFO] FFmpeg found in PATH. Great!
)
echo.

echo [INFO] Checking for .env file...
if not exist .env (
    echo [INFO] Creating .env file...
    echo # OpenAI API key for ChatGPT and Whisper API > .env
    echo OPENAI_API_KEY=your_api_key_here >> .env
    echo. >> .env
    echo # Additional settings (optional) >> .env
    echo # WHISPER_MODEL=base  # tiny, base, small, medium, large >> .env
    echo # WHISPER_LANGUAGE=ru  # ru, en, auto >> .env
    echo # CHATGPT_MODEL=gpt-4o  # gpt-4o, gpt-4-turbo, gpt-3.5-turbo >> .env
    echo [INFO] .env file created. Please edit it to add your OpenAI API key.
) else (
    echo [INFO] .env file already exists.
)

echo [INFO] Checking data and temp directories...
if not exist "data" (
    mkdir data
    echo [INFO] Created data directory.
)
if not exist "data\temp" (
    mkdir "data\temp"
    echo [INFO] Created data\temp directory.
)
echo.

echo [INFO] Checking main component installation...
python -c "import torch; import numpy; import scipy; import sounddevice; print('Successfully imported base libraries')" 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] Failed to import base libraries. Some components may not be installed.
) else (
    echo [SUCCESS] Base libraries installed correctly.
)

echo.
echo ==============================================
echo             Installation Complete!
echo ==============================================
echo.
echo To run the application, use:
echo   python main.py
echo.
echo Remember to set your OpenAI API key in the .env file!
echo.
pause