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
    echo [WARNING] FFmpeg not found in PATH.
    echo [INFO] Attempting to install ffmpeg-python package...
    
    pip install ffmpeg-python
    
    if %errorlevel% neq 0 (
        echo [WARNING] Failed to install ffmpeg-python. This might affect audio processing.
    ) else {
        echo [INFO] Successfully installed ffmpeg-python package.
    }
    
    echo [INFO] For best performance, you should also install the FFmpeg binary:
    echo   1. Download from https://ffmpeg.org/download.html
    echo   2. Add the bin directory to your PATH
    echo   3. Alternatively, you can download automated installer from https://github.com/BtbN/FFmpeg-Builds/releases
    
    choice /C YNC /M "Do you want to: [Y] Continue without FFmpeg, [N] Stop to install it manually, [C] Try auto-download"
    
    if %errorlevel% equ 2 (
        echo.
        echo [INFO] Please install FFmpeg, then run this script again.
        echo       1. Download from https://ffmpeg.org/download.html
        echo       2. Extract the archive
        echo       3. Add the bin directory to your PATH
        echo.
        pause
        exit /b 1
    ) else if %errorlevel% equ 3 (
        echo [INFO] Attempting to download FFmpeg automatically...
        
        :: Create temp directory for download
        if not exist "temp" mkdir temp
        
        :: Check OS architecture
        echo [INFO] Checking system architecture...
        if defined PROCESSOR_ARCHITEW6432 (
            echo [INFO] Detected 64-bit OS with 32-bit process
            set ARCH=64
        ) else (
            if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
                echo [INFO] Detected 64-bit OS
                set ARCH=64
            ) else (
                echo [INFO] Detected 32-bit OS
                set ARCH=32
            )
        )
        
        :: Download the FFmpeg build
        if "%ARCH%"=="64" (
            echo [INFO] Downloading 64-bit FFmpeg...
            curl -L -o temp\ffmpeg.zip https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip
        ) else (
            echo [INFO] Downloading 32-bit FFmpeg...
            curl -L -o temp\ffmpeg.zip https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win32-gpl.zip
        )
        
        :: Extract the downloaded file
        echo [INFO] Extracting FFmpeg...
        powershell -command "Expand-Archive -Path 'temp\ffmpeg.zip' -DestinationPath 'temp' -Force"
        
        :: Copy ffmpeg.exe to the project directory
        echo [INFO] Copying FFmpeg to the project directory...
        for /d %%D in (temp\ffmpeg*) do (
            copy "%%D\bin\ffmpeg.exe" .
            copy "%%D\bin\ffprobe.exe" .
        )
        
        :: Clean up temporary files
        echo [INFO] Cleaning up...
        rmdir /s /q temp
        
        echo [SUCCESS] FFmpeg has been installed to the project directory.
        echo [INFO] You can now use FFmpeg for audio processing without adding it to PATH.
    )
) else (
    echo [INFO] FFmpeg found in PATH. Great!
)
echo.

echo [INFO] Installing ffmpeg-python package for Python integration...
pip install ffmpeg-python
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

echo [INFO] Checking FFmpeg integration...
python -c "import ffmpeg; print('Successfully imported ffmpeg-python')" 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] Failed to import ffmpeg-python. Audio transcription might not work correctly.
) else (
    echo [SUCCESS] FFmpeg Python integration installed correctly.
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