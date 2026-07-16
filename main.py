"""
Основной файл для запуска приложения аудио-ассистента для встреч
"""
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox
from dotenv import load_dotenv

# Добавляем текущую директорию в PATH для импорта модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Исправление для PyInstaller --noconsole: перенаправляем вывод в никуда, 
# чтобы print() не вызывал ошибку 'NoneType' object has no attribute 'write'
if sys.stdout is None:
    class DummyWriter:
        def write(self, x): pass
        def flush(self): pass
    sys.stdout = DummyWriter()
if sys.stderr is None:
    sys.stderr = sys.stdout

# Загружаем .env из %LOCALAPPDATA%\MDelta Meetings\.env
# (туда же где temp-директория — доступно на запись даже при установке в Program Files).
# get_app_dir() автоматически мигрирует данные из старой папки "AI Meetings".
from utils.appdirs import get_app_dir
_env_dir = get_app_dir()
_env_path = os.path.join(_env_dir, '.env')
# Если в LOCALAPPDATA нет .env — пробуем рядом с exe (для dev-запуска)
if not os.path.exists(_env_path):
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path)

class _SplashWriter:
    """Перехватывает stdout во время загрузки модели и обновляет splash progress bar.

    _ggml_model_path печатает '\\r[WhisperNet] Скачивание: XX%' на каждый чанк.
    Мы парсим процент и обновляем Canvas + вызываем root.update() чтобы окно не зависало.
    """
    _PCT_RE = re.compile(r'(\d+)%')

    def __init__(self, root, canvas, label, orig=None):
        self._root = root
        self._canvas = canvas
        self._label = label
        self._orig = orig  # исходный stdout для pass-through (dev mode)

    def write(self, text):
        if self._orig:
            self._orig.write(text)
        m = self._PCT_RE.search(text)
        if m and 'Скачив' in text:  # 'Скачив'
            pct = int(m.group(1))
            # Прогресс скачивания занимает диапазон 0.4–0.75 общей полосы
            overall = 0.4 + (pct / 100.0) * 0.35
            self._canvas.delete('progress')
            self._canvas.create_rectangle(0, 0, 400 * overall, 8,
                                          fill='#1677FF', width=0, tags='progress')
            self._label['text'] = f'Скачивание модели Whisper: {pct}%'
            try:
                self._root.update()
            except Exception:
                pass

    def flush(self):
        if self._orig:
            self._orig.flush()


def main():
    """
    Основная функция для запуска приложения
    """
    # Создаем корневое окно Tkinter (splash в фирменном стиле MDelta)
    root = tk.Tk()
    root.title("Загрузка MDelta Meetings...")
    root.geometry("500x300")
    root.configure(bg="white")

    # Логотип-дельта + название (как в MDelta)
    logo_canvas = tk.Canvas(root, width=48, height=48, bg="white", highlightthickness=0)
    logo_canvas.pack(pady=(18, 0))
    logo_canvas.create_polygon(24, 4, 44, 42, 4, 42, fill="#1677FF", outline="")
    logo_canvas.create_line(13, 38, 20, 22, 24, 30, 28, 18, 35, 38,
                            fill="white", width=3, joinstyle=tk.ROUND, capstyle=tk.ROUND)

    title_label = tk.Label(root, text="MDelta Meetings", font=("Segoe UI", 18, "bold"),
                           bg="white", fg="#1F1F1F")
    title_label.pack(pady=(4, 0))

    description_label = tk.Label(root,
                                text="Запись, транскрипция и саммари встреч",
                                font=("Segoe UI", 10), bg="white", fg="#8C8C8C")
    description_label.pack(pady=5)

    loading_label = tk.Label(root, text="Инициализация компонентов...",
                             font=("Segoe UI", 11), bg="white", fg="#1F1F1F")
    loading_label.pack(pady=12)

    progress = tk.Label(root, text="Подождите...", font=("Segoe UI", 9),
                        bg="white", fg="#8C8C8C")
    progress.pack(pady=4)

    # Создаем полосу прогресса
    progress_bar = tk.Canvas(root, width=400, height=8, bg="#F0F0F0", highlightthickness=0)
    progress_bar.pack(pady=10)

    # Функция для обновления полосы прогресса
    def update_progress(value, text):
        progress_bar.delete("progress")
        progress_bar.create_rectangle(0, 0, 400 * value, 8, fill="#1677FF", width=0, tags="progress")
        progress["text"] = text
        root.update()
    
    # Обновляем окно
    root.update()
    
    try:
        # Инициализируем компоненты
        update_progress(0.1, "Инициализация компонента захвата аудио...")
        
        from src.audio_capture import AudioCapture
        audio_capture = AudioCapture()
        
        # Модель НЕ скачивается при старте: SpeechRecognizer инициализируется
        # лениво (прогрев только если локальная модель уже на диске).
        update_progress(0.4, "Инициализация распознавания речи...")

        from src.speech_recognition import SpeechRecognizer
        _prev_stdout = sys.stdout
        sys.stdout = _SplashWriter(root, progress_bar, progress, orig=_prev_stdout)
        try:
            speech_recognizer = SpeechRecognizer()
        finally:
            sys.stdout = _prev_stdout
        
        update_progress(0.6, "Инициализация клиента ChatGPT...")
        
        from src.chatgpt_client import ChatGPTClient
        chatgpt_client = ChatGPTClient()
        
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