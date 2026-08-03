# MDelta Meetings — Аудио-ассистент для встреч

Запись, транскрипция и умное саммари встреч. Desktop-приложение экосистемы **MDelta**
с интеграцией LLM (Inference: OpenAI / LM Studio / Ollama — или MDelta API).

## Возможности

- Запись микрофона и системного звука одновременно (WASAPI loopback);
  пункт **«Устройство по умолчанию (ОС)»** следует за выбором устройств в Windows
- Кнопки **копирования** транскрипта (с метками времени и спикерами) и саммари
- Распознавание речи — выбор источника в настройках (в т.ч. после установки):
  - **Локально**: **WhisperNet** (C# + whisper.net + Vulkan GPU — любой GPU через DirectX)
    с fallback на **faster-whisper** (CTranslate2, CPU int8)
  - **Удалённый сервер**: любой OpenAI-совместимый `/v1/audio/transcriptions` —
    LM Studio, speaches / faster-whisper-server, vLLM, облачный OpenAI
- Голосовая активация (Silero VAD / RMS fallback) — без ложных срабатываний на фон
- **Диаризация спикеров** по окончании записи — обе дорожки:
  микрофон → «Участник 1/2/…», системный звук → «Собеседник 1/2/…»
- Саммари встречи — провайдер на выбор (секция «ИЛИ» в настройках):
  - **Inference** — OpenAI API или любой OpenAI-совместимый сервер (LM Studio, Ollama, vLLM)
  - **MDelta API** — корпоративная RAG-платформа MDelta (JWT-авторизация, `/api/chat`)
- UI на Flutter (Flet) в дизайн-системе MDelta (Ant Design v5, светлая тема, фирменный логотип)
- Настройки сохраняются в `.env` через UI-диалог; данные старой установки «AI Meetings»
  переносятся в `%LOCALAPPDATA%\MDelta Meetings` автоматически

## Установка для конечного пользователя

Запустите `dist\MDelta_Meetings_Setup_v*.exe` — мастер установит приложение и предложит
выбрать локальную модель Whisper **или пропустить загрузку** (вариант «Не загружать
локальную модель» — для работы с удалённым Whisper-сервером).

Модель **не скачивается ни при установке, ни при запуске приложения** — только при первом
нажатии «Запись» (в `%LOCALAPPDATA%\MDelta Meetings\models\`). Если выбран удалённый
источник, при старте записи проверяется доступность сервера; ошибка (сервер недоступен /
не настроен) показывается в приложении и запись не начинается.

## Dev: сборка

### Требования

- Windows 10/11 64-bit (WASAPI, Vulkan)
- Python 3.11–3.13 — **только обычный установщик с python.org**, не Microsoft Store
  (Store-версия виртуализирует записи в `%LOCALAPPDATA%` через MSIX LocalCache —
  Python «видит» скачанные модели, а WhisperService.exe нет)
- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/8.0) — для сборки WhisperService
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
├── whisper_service/           # C# .NET 10 сервис транскрипции (whisper.net + Vulkan)
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
├── MDelta_Meetings.spec           # PyInstaller spec
├── version.txt                # Единый источник версии (например: 1.0.0)
└── dist/                      # Артефакты сборки (не в git)
    ├── MDelta_Meetings.exe
    └── MDelta_Meetings_Setup_v*.exe
```

### Шаг 1: Создать чистый venv для сборки

```powershell
python -m venv build_venv
build_venv\Scripts\pip install faster-whisper numpy sounddevice pyaudiowpatch `
    openai python-dotenv requests pyinstaller flet
```

**Важно:** НЕ устанавливать torch, tensorflow, keras, transformers в build_venv.  
faster-whisper использует CTranslate2 (не torch) — бандл получается компактнее.

### Шаг 2: Собрать WhisperService (.NET 10)

```powershell
dotnet publish whisper_service/WhisperService.csproj -c Release -r win-x64 --self-contained true -o data/whisper_service
```

Результат: `data/whisper_service/WhisperService.exe` + Vulkan runtime DLL.

### Шаг 3: Собрать MDelta_Meetings.exe

```powershell
build_venv\Scripts\python.exe -m PyInstaller MDelta_Meetings.spec --clean
```

Результат: `dist\MDelta_Meetings.exe` (single-file bundle).

### Шаг 4: Собрать инсталлятор

```powershell
cd installer
.\build_now.ps1
```

Результат: `dist\MDelta_Meetings_Setup_v<version>.exe`.

**Что делает build_now.ps1:**
1. Проверяет наличие `dist\MDelta_Meetings.exe` и `data\whisper_service\WhisperService.exe`
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
| Имя инсталлятора | `build_now.ps1` патчит: `MDelta_Meetings_Setup_v1.0.0.exe` |
| Метаданные инсталлятора (Properties) | `build_now.ps1` патчит `VersionInfoVersion` и `VersionInfoProductVersion` в `setup.iss` |
| Экран готовности Inno Setup | `setup.iss` использует `{#AppVersion}` напрямую |

> **Чтобы выпустить новую версию** — достаточно обновить `version.txt` и запустить сборку.

### Сборка в GitHub Actions

При пуше в `master` (или ручном запуске через *workflow_dispatch*) CI автоматически:
1. Собирает WhisperService через `dotnet publish`
2. Прогоняет тесты (`pytest tests/`)
3. Упаковывает `MDelta_Meetings.exe` через PyInstaller
4. Собирает `MDelta_Meetings_Setup_v*.exe` через Inno Setup
5. Публикует инсталлятор как **Artifact** (хранится 7 дней)

Файл пайплайна: `.github/workflows/build.yml`.

## Настройка (.env)

При установке создаётся `%LOCALAPPDATA%\MDelta Meetings\.env` (не перезаписывается при переустановке).  
Для dev-запуска: скопируйте `.env.example` → `.env` в корне репозитория.

Настройки также можно изменить через кнопку ⚙️ в приложении — они сохраняются в тот же `.env`.

| Переменная | По умолчанию | Описание |
|---|---|---|
| `LLM_PROVIDER` | `inference` | Провайдер LLM: `inference` (OpenAI-совместимый) или `mdelta` (MDelta API) |
| `OPENAI_API_KEY` | — | Ключ OpenAI (обязателен для облака) |
| `OPENAI_API_BASE` | пусто | URL для LM Studio / Ollama |
| `CHATGPT_MODEL` | `gpt-4o` | Модель LLM |
| `MDELTA_API_URL` | пусто | URL MDelta API (например `https://mdrag.example.com`) |
| `MDELTA_USERNAME` | пусто | Логин MDelta |
| `MDELTA_PASSWORD` | пусто | Пароль MDelta |
| `WHISPER_MODE` | `local` | Источник STT: `local` или `remote` |
| `WHISPER_MODEL` | `base` | Размер локальной модели (tiny/base/small/medium/large) |
| `WHISPER_REMOTE_URL` | пусто | URL удалённого Whisper-сервера (`.../v1`) |
| `WHISPER_REMOTE_KEY` | пусто | API-ключ удалённого сервера (если требуется) |
| `WHISPER_REMOTE_MODEL` | `whisper-1` | Имя модели на удалённом сервере |
| `WHISPER_LANGUAGE` | `ru` | Язык распознавания |

Примеры `OPENAI_API_BASE`:
- LM Studio: `http://127.0.0.1:1234/v1`
- Ollama: `http://127.0.0.1:11434/v1`

## Провайдеры LLM (саммаризация)

Секция «Обработка и саммаризация (LLM)» в настройках — переключатель ИЛИ:

- **Inference** — OpenAI SDK / LM Studio Runtime API. Ключ, Base URL и модель задаются в UI;
  кнопка 🔄 загружает список моделей с сервера (`GET /v1/models`).
- **MDelta API** — вход по логину/паролю (JWT `POST /api/auth/login`), диалог через
  `POST /api/chat`. Модель и RAG-пайплайн выбираются на стороне платформы MDelta.
  Кнопка «Проверить подключение» выполняет тестовый логин.

## Бэкенды транскрипции

Секция «Распознавание речи (Whisper)» в настройках — переключатель ИЛИ:
**Локальная модель** (WhisperNet → faster-whisper) или **Удалённый сервер**.

### Remote Whisper (удалённый сервер)

Достаточно указать URL сервера (схема `http://` подставится сама) — тип API
определяется автоматически:

- **OpenAI-совместимый** — `POST .../v1/audio/transcriptions` (multipart WAV):
  LM Studio, [speaches](https://github.com/speaches-ai/speaches) / faster-whisper-server,
  vLLM, облачный OpenAI Audio API. Обнаруживается по `GET /v1/models` → 200.
- **Native whisper.cpp server** — `POST /inference`: сервер отвечает, но `/v1/models`
  не отдаёт. Модель загружена на самом сервере, поле «Модель» игнорируется.
  Пример: `192.168.88.55:8082`.

Кнопка 🔄 в настройках загружает список моделей (для OpenAI-совместимых) или
подтверждает доступность native-сервера. Ошибки (сервер недоступен/не настроен)
показываются при старте записи — скрытой загрузки локальной модели не происходит,
fallback на локальную срабатывает только если она уже скачана.

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
Работает без GPU. Модели скачиваются при первой транскрипции в `%LOCALAPPDATA%\MDelta Meetings\models\faster-whisper-<name>\`.

Если доступна CUDA — используется GPU (float16). Логика выбора: `speech_recognition.py`, функция `_select_ct2_device()`.

### GGML-модели для WhisperNet

GGML `.bin` файлы (формат whisper.cpp) скачиваются из HuggingFace в `%LOCALAPPDATA%\MDelta Meetings\models\`:

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

## Диаризация спикеров

После остановки записи (кнопка **Стоп**) приложение автоматически анализирует весь записанный звук с микрофона
и расставляет метки по участникам встречи.

Метки в транскрипте меняются с «Я» на «Участник 1», «Участник 2» и т.д. с цветовым выделением.
Если обнаружен только один говорящий, метки остаются «Я».

**Требования:** установленный пакет `sherpa-onnx` (`pip install sherpa-onnx`).  
Без него функция недоступна, остальное приложение работает в обычном режиме.

При первом использовании автоматически скачиваются модели (~15 МБ) в
`%LOCALAPPDATA%\MDelta Meetings\models\diarization\`:
- Segmentation model — [pyannote/segmentation-3.0](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models) (~6 МБ)
- Embedding model — [3D-Speaker eres2net](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recognition-models) (~9 МБ)

## Известные ограничения

- Windows only (WASAPI, Vulkan)
- При первой транскрипции скачивается модель Whisper (если выбран локальный источник) (~75–3100 MB в зависимости от размера)
- Silero VAD недоступен в production-бандле (нет torch) — используется RMS VAD
- Диаризация работает только с записью микрофона (не системный звук) и запускается постфактум
