@echo off
echo ====================================
echo   AI Meetings - Minimal Install
echo ====================================
echo.

echo Installing only essential dependencies...
echo.

echo 1. Installing comtypes (for Windows audio)...
pip install comtypes

echo.
echo 2. Installing audio libraries...
pip install sounddevice numpy scipy

echo.
echo 3. Installing OpenAI...
pip install openai

echo.
echo 4. Installing other essentials...
pip install python-dotenv

echo.
echo ====================================
echo Basic dependencies installed!
echo.
echo To install ALL dependencies (including Whisper), run:
echo   pip install -r requirements.txt
echo.
echo To run the application:
echo   python main.py
echo ====================================
pause
