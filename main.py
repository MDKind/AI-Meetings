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
        
        # Запускаем Flet UI
        import flet as ft
        from src.flet_ui import FletAudioAssistantUI
        
        def main_flet(page: ft.Page):
            app = FletAudioAssistantUI(
                page=page,
                audio_capture=audio_capture,
                speech_recognizer=speech_recognizer,
                chatgpt_client=chatgpt_client,
                realtime_assistant=None, # will add later if needed
                env_path=_env_path
            )
        
        # Закрываем окно загрузки
        root.destroy()
        
        ft.app(target=main_flet)
        
    except ModuleNotFoundError as e:
        import tkinter.messagebox as messagebox
        messagebox.showerror(
            "Ошибка импорта модуля",
            f"Не удалось загрузить модуль: {str(e)}.\n"
            "Попробуйте переустановить приложение."
        )
        if 'root' in locals() and root.winfo_exists():
            root.destroy()

    except RuntimeError as e:
        import tkinter.messagebox as messagebox
        messagebox.showerror("Ошибка запуска", str(e))
        if 'root' in locals() and root.winfo_exists():
            root.destroy()

    except Exception as e:
        import tkinter.messagebox as messagebox
        messagebox.showerror("Ошибка", f"Ошибка при инициализации приложения: {str(e)}")
        if 'root' in locals() and root.winfo_exists():
            root.destroy()

if __name__ == "__main__":
    main()