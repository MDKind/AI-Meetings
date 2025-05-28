# AI Meetings - Аудио-ассистент для встреч

Приложение для записи и обработки аудио встреч с интеграцией ChatGPT.

## Возможности

- 🎤 Запись звука с микрофона
- 🔊 Запись системного звука (YouTube, музыка, звонки)
- 🗣️ Распознавание речи (Whisper)
- 🤖 Интеграция с ChatGPT
- 📝 Автоматическое создание саммари встреч
- 💾 Сохранение и загрузка истории

## Быстрый старт

### 1. Установка

```bash
# Минимальная установка (без распознавания речи)
minimal_install.bat

# Или полная установка
pip install -r requirements.txt
```

### 2. Настройка

Создайте файл `.env` в корневой папке:
```
OPENAI_API_KEY=ваш_ключ_api
```

### 3. Запись системного звука

Для записи звука из YouTube/браузера/приложений:

```bash
# Проверьте доступные устройства
python tools\diagnose_audio_devices.py

# Настройте Virtual Cable (если нужно)
scripts\setup_cable_audio.bat
```

**Важно:** Выберите "Stereo Mix" или "CABLE Output" как устройство ввода в приложении.

### 4. Запуск

```bash
python main.py
```

## Структура проекта

```
AI_Meetings/
├── main.py              # Основной файл запуска
├── minimal_install.bat  # Установщик
├── src/                 # Исходный код
├── docs/               # Документация
├── tools/              # Утилиты для диагностики
└── scripts/            # Вспомогательные скрипты
```

## Решение проблем

### Не записывается звук из браузера?
1. Включите Stereo Mix в настройках Windows
2. Или установите [VB-Audio Virtual Cable](https://vb-audio.com/Cable/)
3. См. `docs/RECORD_YOUTUBE_AUDIO.md`

### Ошибки при запуске?
```bash
# Проверка зависимостей
python tools\check_dependencies.py

# Тест запуска
python tools\test_startup.py
```

## Документация

- `docs/SYSTEM_AUDIO_SETUP.md` - Настройка записи системного звука
- `docs/VIRTUAL_CABLE_AUDIO_SETUP.md` - Настройка Virtual Cable
- `docs/TROUBLESHOOTING_SUMMARY.md` - Решение всех проблем

## Требования

- Windows 10/11
- Python 3.8+
- Микрофон (для записи голоса)
- Stereo Mix или Virtual Cable (для записи системного звука)
