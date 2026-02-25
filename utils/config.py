import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройки аудио
AUDIO_SETTINGS = {
    'format': 'int16',     # Формат аудио (16-бит целое)
    'channels': 1,         # Моно
    'rate': 16000,         # Частота дискретизации (Гц)
    'chunk_size': 1024,    # Размер чанка для обработки
    'silence_threshold': 300,  # Порог тишины
    'silence_duration': 2.0,   # Длительность тишины для сегментации (сек)
}

# Настройки для распознавания речи
SPEECH_RECOGNITION = {
    'default_model': os.getenv('WHISPER_MODEL', 'base'),      # Размер модели Whisper (tiny, base, small, medium, large)
    'default_language': os.getenv('WHISPER_LANGUAGE', 'ru'),  # Язык по умолчанию (ru, en, auto)
    'temp_dir': os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'temp')
}

# Настройки для ChatGPT / OpenAI-compatible API
CHATGPT_SETTINGS = {
    'api_key': os.getenv('OPENAI_API_KEY'),                    # API ключ берется из .env
    'api_base_url': os.getenv('OPENAI_API_BASE', ''),          # Кастомный base URL (например LM Studio: http://127.0.0.1:1234/v1)
    'default_model': os.getenv('CHATGPT_MODEL', 'gpt-4o'),    # Модель по умолчанию
    'max_tokens': 2000,                                        # Максимальное количество токенов в ответе
    # Системный промпт для ChatGPT
    'system_prompt': """
    Вы ассистент для ответов на вопросы во время встречи.
    Отвечайте кратко и по существу на заданные вопросы.
    Если вопрос не задан, просто анализируйте текст и собирайте информацию для саммари встречи.
    """
}

# Настройки UI
UI_SETTINGS = {
    'window_title': 'Аудио-ассистент для встреч',
    'window_size': '900x700',
    'font_size': 10
}

# Создаем временную директорию, если её нет
if not os.path.exists(SPEECH_RECOGNITION['temp_dir']):
    try:
        os.makedirs(SPEECH_RECOGNITION['temp_dir'], exist_ok=True)
        print(f"Создана директория для временных файлов: {SPEECH_RECOGNITION['temp_dir']}")
    except Exception as e:
        print(f"Ошибка при создании директории для временных файлов: {e}")
        # Используем системную временную директорию в случае ошибки
        import tempfile
        SPEECH_RECOGNITION['temp_dir'] = tempfile.gettempdir()
        print(f"Используется системная временная директория: {SPEECH_RECOGNITION['temp_dir']}")