@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
::  AI Meetings — Post-install dependency setup
::  Called by InnoSetup [Run] section after files are copied
:: ============================================================

set "APP_DIR=%~dp0"
set "LOG_FILE=%APP_DIR%install_deps.log"
set "REQ_FILE=%APP_DIR%requirements.txt"

echo ====================================================== >> "%LOG_FILE%"
echo AI Meetings — Dependency Installation >> "%LOG_FILE%"
echo Started: %DATE% %TIME% >> "%LOG_FILE%"
echo ====================================================== >> "%LOG_FILE%"

echo.
echo ============================================================
echo   AI Meetings - Установка зависимостей Python
echo ============================================================
echo   Лог сохраняется в: %LOG_FILE%
echo ============================================================
echo.

:: ── 1. Check Python ──────────────────────────────────────────
echo [1/5] Проверка Python...
python --version >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo ОШИБКА: Python не найден в PATH.
    echo Python не найден. >> "%LOG_FILE%"
    echo.
    echo Установите Python 3.8+ с сайта python.org
    echo и убедитесь, что при установке была отмечена опция
    echo "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do (
    echo     Найден: %%v
    echo Используется: %%v >> "%LOG_FILE%"
)

:: ── 2. Upgrade pip ───────────────────────────────────────────
echo.
echo [2/5] Обновление pip...
python -m pip install --upgrade pip >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo ПРЕДУПРЕЖДЕНИЕ: Не удалось обновить pip, продолжаем...
    echo pip upgrade failed ^(non-critical^) >> "%LOG_FILE%"
)
echo     OK

:: ── 3. Core deps (fast) ──────────────────────────────────────
echo.
echo [3/5] Основные зависимости (numpy, openai, sounddevice...)
python -m pip install ^
    numpy>=1.20.0 ^
    openai>=1.0.0 ^
    python-dotenv>=1.0.0 ^
    sounddevice>=0.4.6 ^
    scipy>=1.8.0 ^
    pydub>=0.25.1 ^
    requests>=2.28.0 ^
    pillow>=9.0.0 ^
    >> "%LOG_FILE%" 2>&1

if %errorlevel% neq 0 (
    echo ОШИБКА: Не удалось установить основные зависимости.
    echo Core deps install FAILED >> "%LOG_FILE%"
    echo Проверьте лог: %LOG_FILE%
    pause
    exit /b 1
)
echo     OK

:: ── 4. Windows audio libs ────────────────────────────────────
echo.
echo [4/5] Windows Audio (pyaudio, comtypes, pycaw...)
python -m pip install pyaudio>=0.2.11 >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo ПРЕДУПРЕЖДЕНИЕ: pyaudio не установлен ^(попробуем без него^)
    echo pyaudio install failed >> "%LOG_FILE%"
)

python -m pip install ^
    comtypes>=1.1.10 ^
    pycaw>=20220416 ^
    >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo ПРЕДУПРЕЖДЕНИЕ: comtypes/pycaw не установлены
    echo comtypes/pycaw install failed >> "%LOG_FILE%"
)
echo     OK (Windows audio)

:: ── 5. PyTorch + Whisper (heavy, ~700 MB) ───────────────────
echo.
echo [5/5] PyTorch + Whisper (это займет 5-15 минут, ~700 МБ)
echo       Не закрывайте это окно!
echo.

python -m pip install ^
    torch>=2.0.0 ^
    torchaudio>=2.0.0 ^
    --index-url https://download.pytorch.org/whl/cpu ^
    >> "%LOG_FILE%" 2>&1

if %errorlevel% neq 0 (
    echo ОШИБКА: Не удалось установить PyTorch.
    echo PyTorch install FAILED >> "%LOG_FILE%"
    echo Проверьте интернет-соединение и лог: %LOG_FILE%
    pause
    exit /b 1
)

python -m pip install openai-whisper>=20231117 >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo ОШИБКА: Не удалось установить Whisper.
    echo Whisper install FAILED >> "%LOG_FILE%"
    pause
    exit /b 1
)
echo     OK

:: ── Done ─────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Установка завершена успешно!
echo ============================================================
echo   Примечание: Silero VAD (~1.8 МБ) будет скачан
echo   автоматически при первом запуске приложения.
echo ============================================================
echo.
echo Finished: %DATE% %TIME% >> "%LOG_FILE%"
echo SUCCESS >> "%LOG_FILE%"

timeout /t 4 >nul
exit /b 0
