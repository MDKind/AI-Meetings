@echo off
echo ====================================
echo   AI Meetings - Minimal Install
echo ====================================
echo.

echo Installing essential dependencies...
echo.

echo 1. Core dependencies...
pip install numpy openai python-dotenv sounddevice

echo.
echo 2. Audio libraries...
pip install scipy pyaudio pydub

echo.
echo 3. PyTorch (CPU, for Whisper and Silero VAD)...
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

echo.
echo 4. Whisper speech recognition...
pip install openai-whisper

echo.
echo 5. Windows audio (optional, for WASAPI loopback)...
pip install comtypes pycaw

echo.
echo ====================================
echo Installation complete!
echo.
echo To run:
echo   python main.py
echo.
echo Note: Silero VAD will be downloaded automatically
echo on first run (~1.8 MB, requires internet).
echo ====================================
pause
