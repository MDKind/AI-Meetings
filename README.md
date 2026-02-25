# AI Meetings — Аудио-ассистент для встреч

Запись, транскрипция и саммари встреч с интеграцией LLM (OpenAI / LM Studio / Ollama).

## Возможности

- Запись микрофона и системного звука одновременно
- Распознавание речи (Whisper) с определением говорящего (я / собеседник)
- Голосовая активация (Silero VAD) — без ложных срабатываний на фон
- Интеграция с OpenAI API и любым OpenAI-совместимым сервером
- Саммари встречи по кнопке (не в реальном времени)

## Установка

### Вариант А — Установщик (рекомендуется)

```
winget install JRSoftware.InnoSetup   # один раз
cd installer
.\build_installer.ps1                 # собрать AI_Meetings_Setup.exe
```

Запустите `dist\AI_Meetings_Setup.exe` — мастер установит Python-зависимости,
FFmpeg и настроит `.env` с вашим API-ключом.

### Вариант Б — Вручную

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install openai-whisper numpy openai python-dotenv sounddevice scipy pydub pyaudio comtypes pycaw
```

Скопируйте `.env.example` → `.env` и вставьте ключ:

```
OPENAI_API_KEY=sk-...
```

## Запуск

```bash
python main.py
```

## Настройка

Все параметры — в файле `.env` (см. `.env.example`):

| Переменная | По умолчанию | Описание |
|---|---|---|
| `OPENAI_API_KEY` | — | Ключ OpenAI (обязателен для облака) |
| `OPENAI_API_BASE` | пусто | URL для LM Studio / Ollama |
| `CHATGPT_MODEL` | `gpt-4o` | Модель LLM |
| `WHISPER_MODEL` | `base` | Размер модели Whisper (tiny/base/small/medium/large) |
| `WHISPER_LANGUAGE` | `ru` | Язык распознавания |

Примеры Base URL:
- LM Studio: `http://127.0.0.1:1234/v1`
- Ollama: `http://127.0.0.1:11434/v1`

## Запись системного звука

Для записи звука из браузера / видеозвонков нужен один из вариантов:

1. **Stereo Mix** — включить в Панель управления → Звук → Запись → Показать отключённые устройства
2. **VB-Audio Virtual Cable** — [vb-audio.com/Cable](https://vb-audio.com/Cable/)

Подробнее: `docs/SYSTEM_AUDIO_SETUP.md`, `scripts/setup_cable_audio.bat`

## Структура проекта

```
AI_Meetings/
├── main.py              # Точка входа
├── src/                 # Исходный код (ui, audio_capture, vad, speech_recognition, chatgpt_client...)
├── utils/               # Конфиг и утилиты
├── installer/           # InnoSetup скрипт + build_installer.ps1
├── scripts/             # BAT-скрипты для настройки аудио
├── tools/               # Диагностика (diagnose_audio_devices.py, check_dependencies.py)
└── docs/                # Документация по настройке
```

## Решение проблем

```bash
python tools\diagnose_audio_devices.py   # список аудио устройств
python tools\check_dependencies.py       # проверка зависимостей
python tools\test_startup.py             # тест запуска
```

- Нет звука из браузера → `docs/RECORD_YOUTUBE_AUDIO.md`
- Ошибки comtypes/pycaw → `docs/COMTYPES_ERROR_FIX.md`
- Общие проблемы → `docs/TROUBLESHOOTING_SUMMARY.md`

## Требования

- Windows 10/11 (64-bit)
- Python 3.8+
- Микрофон
- ~1 ГБ свободного места (PyTorch + модели Whisper)
