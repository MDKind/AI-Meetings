@echo off
echo ====================================
echo   AI Meetings - Audio Diagnostics
echo ====================================
echo.

echo Checking audio devices...
echo.

python diagnose_audio_devices.py

echo.
echo ====================================
echo.
echo If no system audio devices found:
echo.
echo 1. Enable Stereo Mix:
echo    - Right-click speaker icon
echo    - Select "Sounds"
echo    - Recording tab
echo    - Right-click - Show Disabled Devices
echo    - Enable "Stereo Mix"
echo.
echo 2. Or install Virtual Cable:
echo    https://vb-audio.com/Cable/
echo.
echo See docs\SYSTEM_AUDIO_SETUP.md for details
echo ====================================
pause
