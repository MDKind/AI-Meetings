"""
Основной файл для запуска приложения аудио-ассистента для встреч
"""
import os
import sys
import tkinter as tk
from tkinter import messagebox
from dotenv import load_dotenv

# Добавляем текущую директорию в PATH для импорта модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Загружаем .env из %LOCALAPPDATA%\AI Meetings\.env
# (туда же где temp-директория — доступно на запись даже при установке в Program Files)
_env_dir = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'AI Meetings')
os.makedirs(_env_dir, exist_ok=True)
_env_path = os.path.join(_env_dir, '.env')
# Если в LOCALAPPDATA нет .env — пробуем рядом с exe (для dev-запуска)
if not os.path.exists(_env_path):
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path)

def main():
    """
    Основная функция для запуска приложения
    """
    # Создаем корневое окно Tkinter
    root = tk.Tk()
    root.title("Загрузка AI Meetings...")
    root.geometry("500x300")
    
    # Добавляем индикатор загрузки
    title_label = tk.Label(root, text="AI Meetings Assistant", font=("Arial", 18, "bold"))
    title_label.pack(pady=10)
    
    description_label = tk.Label(root, 
                                text="Ассистент для обработки аудио и генерации саммари встреч",
                                font=("Arial", 10))
    description_label.pack(pady=5)
    
    loading_label = tk.Label(root, text="Инициализация компонентов...", font=("Arial", 12))
    loading_label.pack(pady=20)
    
    progress = tk.Label(root, text="Подождите...", font=("Arial", 10))
    progress.pack(pady=10)
    
    # Создаем полосу прогресса
    progress_bar = tk.Canvas(root, width=400, height=20, bg="white")
    progress_bar.pack(pady=10)
    
    # Функция для обновления полосы прогресса
    def update_progress(value, text):
        progress_bar.delete("progress")
        progress_bar.create_rectangle(0, 0, 400 * value, 20, fill="#4CAF50", tags="progress")
        progress["text"] = text
        root.update()
    
    # Обновляем окно
    root.update()
    
    try:
        # Проверяем конфигурацию API.
        # Для локальных серверов (LM Studio / Ollama) ключ не нужен —
        # достаточно указать OPENAI_API_BASE в .env.
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_API_BASE", "")
        if not api_key and not api_base:
            messagebox.showerror(
                "Ошибка конфигурации",
                "Не найден API ключ и не задан Base URL.\n\n"
                "Вариант 1 — OpenAI:\n"
                "  OPENAI_API_KEY=sk-...\n\n"
                "Вариант 2 — LM Studio / Ollama (ключ не нужен):\n"
                "  OPENAI_API_BASE=http://127.0.0.1:1234/v1\n\n"
                "Создайте файл .env в папке с приложением."
            )
            root.destroy()
            return
        
        # Инициализируем компоненты
        update_progress(0.1, "Инициализация компонента захвата аудио...")
        
        from src.audio_capture import AudioCapture
        audio_capture = AudioCapture()
        
        update_progress(0.4, "Загрузка модели распознавания речи...")
        
        from src.speech_recognition import SpeechRecognizer
        speech_recognizer = SpeechRecognizer()
        
        update_progress(0.6, "Инициализация клиента ChatGPT...")
        
        from src.chatgpt_client import ChatGPTClient
        chatgpt_client = ChatGPTClient()
        
        update_progress(0.7, "Инициализация модуля саммаризации...")
        
        from src.meeting_summarizer import MeetingSummarizer
        meeting_summarizer = MeetingSummarizer(chatgpt_client)
        
        update_progress(0.9, "Создание пользовательского интерфейса...")
        
        # Закрываем окно загрузки
        root.destroy()
        
        # Создаем новое окно для приложения
        app_root = tk.Tk()
        
        # Создаем интерфейс
        from src.ui import AudioAssistantUI
        from src.realtime_meeting_assistant import RealtimeMeetingAssistant
        
        # Создаем ассистента для встреч
        realtime_assistant = RealtimeMeetingAssistant(
            audio_capture=audio_capture,
            speech_recognizer=speech_recognizer,
            chatgpt_client=chatgpt_client,
            meeting_summarizer=meeting_summarizer
        )
        
        # Создаем UI
        ui = AudioAssistantUI(
            app_root,
            audio_capture=audio_capture,
            speech_recognizer=speech_recognizer,
            chatgpt_client=chatgpt_client,
            realtime_assistant=realtime_assistant,
            env_path=_env_path
        )
        
        # Запускаем главный цикл
        app_root.mainloop()
        
    except ModuleNotFoundError as e:
        messagebox.showerror(
            "Ошибка импорта модуля", 
            f"Не удалось импортировать необходимый модуль: {str(e)}.\n"
            "Пожалуйста, убедитесь, что все зависимости установлены:\n"
            "pip install -r requirements.txt"
        )
        root.destroy()
    
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка при инициализации приложения: {str(e)}")
        root.destroy()


if __name__ == "__main__":
    main()