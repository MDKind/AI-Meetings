# AI Meetings — Аудио-ассистент для встреч

Запись, транскрипция и умное саммари встреч с интеграцией LLM (OpenAI / LM Studio / Ollama).

## Возможности

- Запись микрофона и системного звука одновременно (WASAPI loopback)
- Распознавание речи — два бэкенда с автоматическим выбором:
  - **WhisperNet** (primary): C# + whisper.net + Vulkan GPU — работает на любом GPU через DirectX
  - **faster-whisper** (fallback): CTranslate2, CPU int8 — 2-4× быстрее openai-whisper без GPU
- Голосовая активация (Silero VAD / RMS fallback) — без ложных срабатываний на фон
- Саммари встречи через OpenAI API или любой OpenAI-совместимый сервер (LM Studio, Ollama)
- Современный UI на Flutter (Flet) с тёмной темой
- Настройки API сохраняются в `.env` через UI-диалог

## Установка для конечного пользователя

Запустите `dist\AI_Meetings_Setup_v*.exe` — мастер установит приложение и предложит ввести API-ключ.  
При первом запуске приложение автоматически скачает модель Whisper (~75–150 MB) в `%LOCALAPPDATA%\AI Meetings\models\`.

## Dev: сборка

### Требования

- Windows 10/11 64-bit (WASAPI, Vulkan)
- Python 3.11 (проверено; 3.13 тоже работает)
- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0) — для сборки WhisperService
- Inno Setup 6 (`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`)

### Структура

```
AI_Meetings/
├── main.py                    # Точка входа (splash + инициализация компонентов)
├── src/
│   ├── flet_ui.py             # Flet UI
│   ├── speech_recognition.py  # WhisperNet + faster-whisper (dual backend)
│   ├── audio_capture.py       # WASAPI захват микрофона + системного звука, VAD, сегментация
│   ├── system_audio_capture.py# WASAPI loopback (pyaudiowpatch)
│   ├── vad.py                 # Silero VAD (torch опционален) + RMS fallback
│   ├── chatgpt_client.py      # OpenAI / совместимый API клиент
│   └── meeting_summarizer.py  # Саммаризация через LLM
├── utils/
│   ├── config.py              # AUDIO_SETTINGS, SPEECH_RECOGNITION, CHATGPT_SETTINGS, UI_SETTINGS
│   └── storage.py
├── whisper_service/           # C# .NET 8 сервис транскрипции (whisper.net + Vulkan)
│   ├── WhisperService.csproj
│   └── Program.cs             # Бинарный IPC протокол stdin/stdout с Python
├── tests/
├── installer/
│   ├── setup.iss              # Inno Setup скрипт (пути относительные — патчатся build_now.ps1)
│   ├── build_now.ps1          # Сборка инсталлятора (рекомендуется)
│   ├── assets/                # icon.ico, wizard.bmp, icon_small.bmp
│   └── bundled/ffmpeg/        # ffmpeg.exe, ffprobe.exe (не в git)
├── data/
│   └── whisper_service/       # Артефакт dotnet publish (не в git)
├── AI_Meetings.spec           # PyInstaller spec
├── version.txt                # Единый источник версии (например: 1.0.0)
└── dist/                      # Артефакты сборки (не в git)
    ├── AI_Meetings.exe
    └── AI_Meetings_Setup_v*.exe
```

### Шаг 1: Создать чистый venv для сборки

```powershell
python -m venv build_venv
build_venv\Scripts\pip install faster-whisper numpy sounddevice pyaudiowpatch `
    openai python-dotenv requests pyinstaller flet
```

**Важно:** НЕ устанавливать torch, tensorflow, keras, transformers в build_venv.  
faster-whisper использует CTranslate2 (не torch) — бандл получается компактнее.

### Шаг 2: Собрать WhisperService (.NET 8)

```powershell
dotnet publish whisper_service/WhisperService.csproj -c Release -r win-x64 --self-contained true -o data/whisper_service
```

Результат: `data/whisper_service/WhisperService.exe` + Vulkan runtime DLL.

### Шаг 3: Собрать AI_Meetings.exe

```powershell
build_venv\Scripts\python.exe -m PyInstaller AI_Meetings.spec --clean
```

Результат: `dist\AI_Meetings.exe` (single-file bundle).

### Шаг 4: Собрать инсталлятор

```powershell
cd installer
.\build_now.ps1
```

Результат: `dist\AI_Meetings_Setup_v<version>.exe`.

**Что делает build_now.ps1:**
1. Проверяет наличие `dist\AI_Meetings.exe` и `data\whisper_service\WhisperService.exe`
2. Создаёт `assets\` если нет (placeholder иконка/bitmap)
3. Скачивает FFmpeg в `bundled\ffmpeg\` если нет
4. Патчит `setup.iss` (заменяет относительные пути `..\dist` → абсолютные) через `.Replace()` (не regex — нет проблем с backslash)
5. Подставляет версию из `version.txt` в имя файла, метаданные инсталлятора
6. Запускает `ISCC.exe` через оператор `&`

## Релизы и версионирование

Единый источник версии — файл `version.txt` (например, `1.0.0`).

Что обновляется автоматически при сборке:

| Место | Как обновляется |
|---|---|
| Заголовок окна приложения | `flet_ui.py` читает `version.txt` в рантайме (бандл включает файл) |
| Имя инсталлятора | `build_now.ps1` патчит: `AI_Meetings_Setup_v1.0.0.exe` |
| Метаданные инсталлятора (Properties) | `build_now.ps1` патчит `VersionInfoVersion` и `VersionInfoProductVersion` в `setup.iss` |
| Экран готовности Inno Setup | `setup.iss` использует `{#AppVersion}` напрямую |

> **Чтобы выпустить новую версию** — достаточно обновить `version.txt` и запустить сборку.

### Сборка в GitHub Actions

При пуше в `master` (или ручном запуске через *workflow_dispatch*) CI автоматически:
1. Собирает WhisperService через `dotnet publish`
2. Прогоняет тесты (`pytest tests/`)
3. Упаковывает `AI_Meetings.exe` через PyInstaller
4. Собирает `AI_Meetings_Setup_v*.exe` через Inno Setup
5. Публикует инсталлятор как **Artifact** (хранится 7 дней)

Файл пайплайна: `.github/workflows/build.yml`.

## Настройка (.env)

При установке создаётся `%LOCALAPPDATA%\AI Meetings\.env` (не перезаписывается при переустановке).  
Для dev-запуска: скопируйте `.env.example` → `.env` в корне репозитория.

Настройки также можно изменить через кнопку ⚙️ в приложении — они сохраняются в тот же `.env`.

| Переменная | По умолчанию | Описание |
|---|---|---|
| `OPENAI_API_KEY` | — | Ключ OpenAI (обязателен для облака) |
| `OPENAI_API_BASE` | пусто | URL для LM Studio / Ollama |
| `CHATGPT_MODEL` | `gpt-4o` | Модель LLM |
| `WHISPER_MODEL` | `base` | Размер модели (tiny/base/small/medium/large) |
| `WHISPER_LANGUAGE` | `ru` | Язык распознавания |

Примеры `OPENAI_API_BASE`:
- LM Studio: `http://127.0.0.1:1234/v1`
- Ollama: `http://127.0.0.1:11434/v1`

## Бэкенды транскрипции

### WhisperNet (primary, GPU via Vulkan)

C# сервис на основе [whisper.net](https://github.com/sandrohanea/whisper.net) с Vulkan-бэкендом.  
Работает на любом GPU (NVIDIA, AMD, Intel) через DirectX 12 / Vulkan без установки CUDA.

Python запускает `WhisperService.exe` как subprocess и общается по бинарному IPC-протоколу:
- Python → C#: `int32(len)` + WAV bytes
- C# → Python: `int32(len)` + UTF-8 text

При смене языка сервис перезапускается автоматически.  
Если `WhisperService.exe` не найден — автоматический переход на faster-whisper.

### faster-whisper (fallback, CPU)

[faster-whisper](https://github.com/SYSTRAN/faster-whisper) — CTranslate2, int8-квантизация.  
Работает без GPU. Модели скачиваются при первом запуске в `%LOCALAPPDATA%\AI Meetings\models\faster-whisper-<name>\`.

Если доступна CUDA — используется GPU (float16). Логика выбора: `speech_recognition.py`, функция `_select_ct2_device()`.

### GGML-модели для WhisperNet

GGML `.bin` файлы (формат whisper.cpp) скачиваются из HuggingFace в `%LOCALAPPDATA%\AI Meetings\models\`:

| Модель | Размер | Точность |
|---|---|---|
| tiny | ~75 MB | низкая |
| base | ~142 MB | хорошая для коротких фраз |
| small | ~466 MB | хорошая |
| medium | ~1.5 GB | высокая |
| large-v3-turbo | ~1.6 GB | очень высокая, быстрее large |
| large-v3 | ~3.1 GB | максимальная |

## Запись системного звука

Захват звука из браузера / видеозвонков (Teams, Zoom, Meet) — через WASAPI loopback.  
Выберите нужные динамики/наушники в поле **«Системный звук»** в UI.

Если WASAPI loopback не работает:
1. **Stereo Mix** — Панель управления → Звук → Запись → Показать отключённые устройства
2. **VB-Audio Virtual Cable** — [vb-audio.com/Cable](https://vb-audio.com/Cable/)

## VAD (голосовая активация)

Используется для сегментации речи — не записывает тишину и фоновый шум.

- **Silero VAD** (основной): нейросеть 1.8 MB, ~1 мс на чанк, обучена на переговорах. Требует `torch`.
- **RMS VAD** (fallback): простой пороговый детектор, без зависимостей.

В собранном бандле `torch` не включён → всегда используется RMS VAD.  
Для разработки: `pip install torch --index-url https://download.pytorch.org/whl/cpu`

## Известные ограничения

- Windows only (WASAPI, Vulkan)
- При первом запуске скачивается модель Whisper (~75–3100 MB в зависимости от размера)
- Silero VAD недоступен в production-бандле (нет torch) — используется RMS VAD
