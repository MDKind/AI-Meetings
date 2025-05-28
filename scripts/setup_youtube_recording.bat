@echo off
cls
echo ============================================================
echo      КАК ЗАПИСАТЬ ЗВУК ИЗ YOUTUBE/ВИДЕО/МУЗЫКИ
echo ============================================================
echo.
echo ЧТО НУЖНО СДЕЛАТЬ:
echo.
echo 1. ВКЛЮЧИТЬ STEREO MIX В WINDOWS:
echo    - Правый клик на значок звука (возле часов)
echo    - Выбрать "Звуки"
echo    - Вкладка "Запись"
echo    - Правый клик - "Показать отключенные устройства"
echo    - Найти "Stereo Mix" или "Стереомикшер"
echo    - Правый клик - "Включить"
echo.
echo 2. В ПРИЛОЖЕНИИ AI MEETINGS:
echo    - В поле "Устройство ввода" выбрать "Stereo Mix"
echo      (НЕ микрофон!)
echo    - Нажать "Начать запись"
echo    - Включить YouTube/музыку/видео
echo.
echo ============================================================
echo.
echo Сейчас проверим, есть ли у вас Stereo Mix...
echo.
pause

python diagnose_audio_devices.py

echo.
echo ============================================================
echo.
echo ЕСЛИ STEREO MIX НЕ НАЙДЕН:
echo.
echo Вариант 1: Попробуйте включить его в настройках Windows
echo Вариант 2: Установите VB-Audio Virtual Cable
echo           https://vb-audio.com/Cable/
echo.
echo Подробная инструкция: docs\RECORD_YOUTUBE_AUDIO.md
echo ============================================================
pause
