import os
from dotenv import load_dotenv

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
    'temp_dir': os.path.join(
        os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
        'AI Meetings', 'temp'
    ),
}

# ── Настройки LLM (OpenAI / LM Studio) ───────────────────────────────────────
CHATGPT_SETTINGS = {
    'api_key': os.getenv('OPENAI_API_KEY'),
    'api_base_url': os.getenv('OPENAI_API_BASE', ''),
    'default_model': os.getenv('CHATGPT_MODEL', 'gpt-4o'),
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
    'window_title': 'AI Meetings',
    'window_width': 1000,
    'window_height': 700,
    'font_size': 14,
}

# ── Создаём temp-директорию при необходимости ─────────────────────────────────
try:
    os.makedirs(SPEECH_RECOGNITION['temp_dir'], exist_ok=True)
except Exception as e:
    import tempfile
    SPEECH_RECOGNITION['temp_dir'] = tempfile.gettempdir()
    print(f"Не удалось создать temp-директорию, используется системная: {SPEECH_RECOGNITION['temp_dir']}")
