import os
from dotenv import load_dotenv

from utils.appdirs import get_app_dir

# Загружаем переменные окружения из .env файла
load_dotenv()

# ── Настройки аудио ────────────────────────────────────────────────────────────
AUDIO_SETTINGS = {
    'format': 'int16',          # Формат аудио (16-бит целое)
    'channels': 1,              # Моно
    'rate': 16000,              # Частота дискретизации (Гц)
    'chunk_size': 1024,         # Размер чанка для обработки
    'silence_threshold': 300,   # Порог тишины (RMS, int16)

    # Длительность тишины для завершения сегмента речи (сек).
    # 1.2 сек — достаточно чтобы не резать слова, но не тянуть долгие паузы.
    'silence_duration_vad': 1.2,

    # Минимальная длина сегмента (сек).
    # Сегменты короче этого порога Whisper распознаёт с галлюцинациями — пропускаем.
    'min_segment_duration': 0.8,

    # Максимальная длина одного сегмента (сек).
    # Whisper плохо работает с аудио > 30 сек; 20 сек — хороший предел.
    'max_segment_duration': 20.0,
}

# ── Настройки распознавания речи ──────────────────────────────────────────────
SPEECH_RECOGNITION = {
    'default_model': os.getenv('WHISPER_MODEL', 'base'),
    'default_language': os.getenv('WHISPER_LANGUAGE', 'ru'),
    'temp_dir': os.path.join(get_app_dir(), 'temp'),

    # Источник распознавания: 'local' (WhisperNet/faster-whisper)
    # или 'remote' (OpenAI-совместимый сервер: LM Studio, speaches,
    # faster-whisper-server, vLLM, OpenAI Audio API).
    'mode': os.getenv('WHISPER_MODE', 'local'),
    'remote_base_url': os.getenv('WHISPER_REMOTE_URL', ''),
    'remote_api_key': os.getenv('WHISPER_REMOTE_KEY', ''),
    'remote_model': os.getenv('WHISPER_REMOTE_MODEL', 'whisper-1'),
}

# ── Настройки LLM (Inference / MDelta API) ────────────────────────────────────
CHATGPT_SETTINGS = {
    # Провайдер обработки и саммаризации:
    #   'inference' — OpenAI-совместимый API (OpenAI, LM Studio, Ollama, vLLM)
    #   'mdelta'    — MDelta API (RAG-платформа, JWT-авторизация, /api/chat)
    'provider': os.getenv('LLM_PROVIDER', 'inference'),

    'api_key': os.getenv('OPENAI_API_KEY'),
    'api_base_url': os.getenv('OPENAI_API_BASE', ''),
    'default_model': os.getenv('CHATGPT_MODEL', 'gpt-4o'),

    'mdelta_base_url': os.getenv('MDELTA_API_URL', ''),
    'mdelta_username': os.getenv('MDELTA_USERNAME', ''),
    'mdelta_password': os.getenv('MDELTA_PASSWORD', ''),

    'max_tokens': 2000,
    'summary_max_tokens': 4000,
    'system_prompt': (
        'Вы ассистент для ответов на вопросы во время встречи. '
        'Отвечайте кратко и по существу. '
        'Если вопрос не задан, анализируйте текст и собирайте информацию для саммари встречи.'
    ),
}

# ── Настройки UI ──────────────────────────────────────────────────────────────
UI_SETTINGS = {
    'window_title': 'MDelta Meetings',
    'window_width': 1080,
    'window_height': 720,
    'font_size': 14,
}

# ── Дизайн-токены MDelta (Ant Design v5) ─────────────────────────────────────
# Синхронизированы с веб-платформой MDelta: светлая тема, синий primary.
MDELTA_THEME = {
    'primary': '#1677FF',        # Ant Design blue-6 — кнопки, акценты
    'primary_hover': '#4096FF',  # blue-5
    'primary_dark': '#0958D9',   # blue-7
    'bg_layout': '#F5F5F5',      # фон рабочей области
    'bg_container': '#FFFFFF',   # карточки, сайдбар, хедер
    'border': '#F0F0F0',         # разделители
    'text': '#1F1F1F',           # основной текст (~88% black)
    'text_secondary': '#8C8C8C', # вторичный текст (45%)
    'success': '#52C41A',
    'warning': '#FAAD14',
    'error': '#FF4D4F',
    'radius': 8,                 # базовый радиус скругления
}

# ── Создаём temp-директорию при необходимости ─────────────────────────────────
try:
    os.makedirs(SPEECH_RECOGNITION['temp_dir'], exist_ok=True)
except Exception as e:
    import tempfile
    SPEECH_RECOGNITION['temp_dir'] = tempfile.gettempdir()
    print(f"Не удалось создать temp-директорию, используется системная: {SPEECH_RECOGNITION['temp_dir']}")
