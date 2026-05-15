# AI Meetings — Аудио-ассистент для встреч

Запись, транскрипция и умное саммари встреч в стиле **Plaud Note** с интеграцией LLM (OpenAI / LM Studio / Ollama).

## Возможности

- Запись микрофона и системного звука одновременно
- Распознавание речи (faster-whisper / CTranslate2) — 2-4x быстрее openai-whisper
- Голосовая активация (Silero VAD) — без ложных срабатываний на фон
- Интеграция с OpenAI API и любым OpenAI-совместимым сервером
- **Умное саммари (Plaud Note Style):** Выделение главных тем, интеллект-карт и задач (Action Items)
- **Современный UI:** Кроссплатформенный премиум-интерфейс на базе Flutter (Flet)

## Установка для конечного пользователя

Запустите `dist\AI_Meetings_Setup.exe` — мастер установит приложение, FFmpeg и предложит ввести API-ключ.

## Dev: сборка

### Требования

- Windows 10/11 64-bit
- Python 3.13 (проверено на 3.13.7)
- Inno Setup 6 (`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`)

### Структура

```
AI_Meetings/
├── main.py                   # Точка входа
├── src/                      # Исходный код
│   ├── flet_ui.py            # Современный Flet интерфейс
│   ├── speech_recognition.py # faster-whisper (НЕ openai-whisper)
│   ├── vad.py                # Silero VAD + RMS fallback (torch опционален)
│   ├── audio_capture.py      # WASAPI захват
│   └── ...
├── utils/                    # Конфиг и утилиты
├── installer/
│   ├── setup.iss             # InnoSetup скрипт (пути относительные — ..\dist и т.д.)
│   ├── build_now.ps1         # Быстрая сборка инсталлятора (рекомендуется)
│   ├── build_installer.ps1   # Полная сборка с загрузкой FFmpeg
│   ├── assets/               # icon.ico, wizard.bmp, icon_small.bmp
│   └── bundled/ffmpeg/       # ffmpeg.exe, ffprobe.exe (не в git)
├── AI_Meetings.spec          # PyInstaller spec
├── build_venv/               # Чистый venv для PyInstaller (не в git)
└── dist/                     # Артефакты сборки (не в git)
    ├── AI_Meetings.exe       # PyInstaller bundle
    └── AI_Meetings_Setup.exe # InnoSetup инсталлятор
```

### Шаг 1: Создать чистый venv для сборки

```powershell
python -m venv build_venv
build_venv\Scripts\pip install faster-whisper numpy scipy sounddevice pyaudio `
    comtypes pycaw pydub openai python-dotenv requests pillow `
    tiktoken numba llvmlite pyinstaller flet
```

**Важно:** НЕ устанавливать torch, tensorflow, keras, transformers в build_venv.
faster-whisper использует CTranslate2 (не torch) — бандл получается меньше.

### Шаг 2: Собрать AI_Meetings.exe

```powershell
build_venv\Scripts\python.exe -m PyInstaller AI_Meetings.spec --clean
```

Результат: `dist\AI_Meetings.exe` (~613 MB).

### Шаг 3: Собрать инсталлятор

```powershell
cd installer
.\build_now.ps1
```

Результат: `dist\AI_Meetings_Setup.exe`.

**Как работает build_now.ps1:**
1. Проверяет наличие `dist\AI_Meetings.exe`
2. Создаёт `assets\` если нет (placeholder иконка/bitmap)
3. Загружает FFmpeg в `bundled\ffmpeg\` если нет
4. Патчит `setup.iss` (заменяет относительные пути `..\dist` → абсолютные) через `.Replace()` (не regex!)
5. Запускает `ISCC.exe` через оператор `&` (не `Start-Process -Wait`, который зависает в bash)
6. Временный патченный .iss сохраняется в `%TEMP%\ai_meetings_setup.iss`

**Если нужно запустить ISCC вручную (из bash/CI):**
```powershell
# PowerShell напрямую (не через cmd.exe):
/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe `
    -ExecutionPolicy Bypass -NonInteractive `
    -File I:\Work\Dev\Repos\AI_Meetings\installer\build_now.ps1
```

## Релизы и версионирование (CI/CD)

Проект использует систему единого источника правды для версий (Single Source of Truth).
Текущая версия хранится в файле `version.txt` (например, `1.0.0`). 

Для выпуска новой версии достаточно обновить этот файл. Система автоматически:
1. Выведет версию в заголовок окна и интерфейс (Flet).
2. Прошьет версию в метаданные собираемого PyInstaller EXE-файла.
3. Соберет через Inno Setup готовый инсталлятор с правильным именем, например `AI_Meetings_Setup_v1.0.0.exe`.

### Сборка в GitHub Actions
В проекте настроен пайплайн CI/CD (`.github/workflows/build.yml`). 
При пуше в ветку `master` (или при ручном запуске через *workflow_dispatch* во вкладке Actions) GitHub автоматически собирает проект и инсталлятор, который затем доступен для скачивания в разделе **Artifacts**.

## Настройка (.env)

Скопируйте `.env.example` → `.env`:

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

## GPU / Устройство вывода

### NVIDIA (CUDA)
Автоматически используется если установлен CUDA-драйвер. CTranslate2 определяет наличие CUDA через `get_supported_compute_types("cuda")`.

### AMD (ROCm)
`ctranslate2` устанавливается с ROCm-поддержкой (`_rocm_sdk_core` в пакете). На Windows ROCm работает нестабильно — приложение автоматически падает на CPU если ROCm недоступен.

`torch-directml` (AMD GPU через DirectX 12) не поддерживает Python 3.11+ — использовать нельзя.

### CPU (fallback)
Всегда работает. faster-whisper с int8-квантизацией на CPU в 2-4x быстрее openai-whisper.

Логика выбора устройства — `src/speech_recognition.py`, функция `_select_device()`.

## Запись системного звука

Для записи звука из браузера / видеозвонков:

1. **Stereo Mix** — Панель управления → Звук → Запись → Показать отключённые устройства
2. **VB-Audio Virtual Cable** — [vb-audio.com/Cable](https://vb-audio.com/Cable/)

## Решение проблем

```bash
python tools\diagnose_audio_devices.py   # список аудио устройств
python tools\check_dependencies.py       # проверка зависимостей
```

- Нет звука из браузера → `docs/RECORD_YOUTUBE_AUDIO.md`
- Ошибки comtypes/pycaw → `docs/COMTYPES_ERROR_FIX.md`

## Известные ограничения

- Windows only (WASAPI, comtypes)
- Модели Whisper скачиваются при первом запуске (~75 MB для `base`) в `~/.cache/huggingface/`
- torch не включён в бандл — VAD (vad.py) использует RMS-детектор вместо Silero если torch недоступен
