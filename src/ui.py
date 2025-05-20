import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox, filedialog
import threading
import os
import time
import datetime
from utils.config import UI_SETTINGS, SPEECH_RECOGNITION

class AudioAssistantUI:
    """
    Класс для создания пользовательского интерфейса аудио-ассистента
    """
    def __init__(self, root, audio_capture, speech_recognizer, chatgpt_client):
        """
        Инициализирует пользовательский интерфейс
        
        Args:
            root: Корневой элемент Tkinter
            audio_capture: Экземпляр класса AudioCapture
            speech_recognizer: Экземпляр класса SpeechRecognizer
            chatgpt_client: Экземпляр класса ChatGPTClient
        """
        self.root = root
        self.root.title(UI_SETTINGS['window_title'])
        self.root.geometry(UI_SETTINGS['window_size'])
        
        # Устанавливаем компоненты
        self.audio_capture = audio_capture
        self.speech_recognizer = speech_recognizer
        self.chatgpt_client = chatgpt_client
        
        # Флаги состояния
        self.is_recording = False
        self.is_processing = False
        self.input_device_index = None
        self.output_device_index = None
        
        # Создаем пользовательский интерфейс
        self.create_ui()
        
        # Инициализируем список устройств
        self.refresh_devices()
        
        # Устанавливаем обработчик закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_ui(self):
        """
        Создает элементы пользовательского интерфейса
        """
        # Настройка шрифтов
        default_font = ("Arial", UI_SETTINGS['font_size'])
        header_font = ("Arial", UI_SETTINGS['font_size'] + 2, "bold")
        
        # Основной фрейм
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Верхняя панель с управляющими элементами
        control_frame = ttk.LabelFrame(main_frame, text="Управление", padding="5")
        control_frame.pack(fill="x", pady=(0, 5))
        
        # Устройства ввода/вывода
        devices_frame = ttk.Frame(control_frame)
        devices_frame.pack(fill="x", pady=5)
        
        # Устройства ввода (микрофоны)
        input_frame = ttk.LabelFrame(devices_frame, text="Устройство ввода (микрофон)")
        input_frame.grid(row=0, column=0, pady=5, padx=5, sticky="ew")
        
        self.input_device_combobox = ttk.Combobox(input_frame, width=40, font=default_font)
        self.input_device_combobox.pack(fill="x", expand=True, padx=5, pady=5)
        
        # Устройства вывода (наушники, колонки)
        output_frame = ttk.LabelFrame(devices_frame, text="Устройство вывода (наушники, колонки)")
        output_frame.grid(row=0, column=1, pady=5, padx=5, sticky="ew")
        
        self.output_device_combobox = ttk.Combobox(output_frame, width=40, font=default_font)
        self.output_device_combobox.pack(fill="x", expand=True, padx=5, pady=5)
        
        # Кнопка обновления списка устройств
        refresh_frame = ttk.Frame(devices_frame)
        refresh_frame.grid(row=1, column=0, columnspan=2, pady=5, sticky="ew")
        
        ttk.Button(refresh_frame, text="Обновить список устройств", 
                  command=self.refresh_devices, width=25).pack(pady=5)
        
        # Настройки распознавания
        settings_frame = ttk.Frame(control_frame)
        settings_frame.pack(fill="x", pady=5)
        
        ttk.Label(settings_frame, text="Модель Whisper:", font=default_font).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.model_combobox = ttk.Combobox(settings_frame, values=["tiny", "base", "small", "medium", "large"], 
                                          width=10, font=default_font)
        self.model_combobox.current(1)  # base по умолчанию
        self.model_combobox.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(settings_frame, text="Язык:", font=default_font).grid(row=0, column=2, padx=(15, 5), pady=5, sticky="w")
        self.language_combobox = ttk.Combobox(settings_frame, values=["ru", "en", "auto"], 
                                             width=5, font=default_font)
        self.language_combobox.current(0)  # ru по умолчанию
        self.language_combobox.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        
        ttk.Label(settings_frame, text="Модель ChatGPT:", font=default_font).grid(row=0, column=4, padx=(15, 5), pady=5, sticky="w")
        self.chatgpt_model_combobox = ttk.Combobox(settings_frame, values=["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"], 
                                                  width=12, font=default_font)
        self.chatgpt_model_combobox.current(0)  # gpt-4o по умолчанию
        self.chatgpt_model_combobox.grid(row=0, column=5, padx=5, pady=5, sticky="w")
        
        # Кнопки управления
        buttons_frame = ttk.Frame(control_frame)
        buttons_frame.pack(fill="x", pady=5)
        
        self.start_button = ttk.Button(buttons_frame, text="Начать запись", 
                                      command=self.toggle_recording, width=15)
        self.start_button.pack(side="left", padx=5)
        
        ttk.Button(buttons_frame, text="Сгенерировать саммари", 
                  command=self.generate_summary, width=20).pack(side="left", padx=5)
        
        ttk.Button(buttons_frame, text="Сохранить разговор", 
                  command=self.save_conversation, width=15).pack(side="left", padx=5)
        
        ttk.Button(buttons_frame, text="Загрузить разговор", 
                  command=self.load_conversation, width=15).pack(side="left", padx=5)
        
        ttk.Button(buttons_frame, text="Очистить историю", 
                  command=self.clear_history, width=15).pack(side="left", padx=5)
        
        # Создаем разделенное окно для одновременного отображения распознанного текста и ответов ChatGPT
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill="both", expand=True, pady=5)
        
        # Создаем вертикальный разделитель панелей (верхняя и нижняя части)
        paned_window = ttk.PanedWindow(content_frame, orient=tk.VERTICAL)
        paned_window.pack(fill="both", expand=True)
        
        # Панель для распознанного текста (верхняя часть)
        text_frame = ttk.LabelFrame(paned_window, text="Распознанный текст", padding=5)
        paned_window.add(text_frame, weight=1)
        
        self.transcription_text = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, 
                                                          font=default_font, height=8)
        self.transcription_text.pack(fill="both", expand=True)
        
        # Панель для ответов ChatGPT (нижняя часть)
        chat_frame = ttk.LabelFrame(paned_window, text="Ответы ChatGPT", padding=5)
        paned_window.add(chat_frame, weight=1)
        
        self.chat_text = scrolledtext.ScrolledText(chat_frame, wrap=tk.WORD, 
                                                 font=default_font, height=8)
        self.chat_text.pack(fill="both", expand=True)
        
        # Создаем вкладки для саммари и настроек
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=5)
        
        # Вкладка для саммари
        summary_frame = ttk.Frame(notebook, padding=5)
        notebook.add(summary_frame, text="Саммари встречи")
        
        self.summary_text = scrolledtext.ScrolledText(summary_frame, wrap=tk.WORD, 
                                                    font=default_font, height=10)
        self.summary_text.pack(fill="both", expand=True)
        
        # Панель статуса
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Добавляем индикатор аудио уровня
        self.audio_level_canvas = tk.Canvas(status_frame, width=100, height=15, bg="white")
        self.audio_level_canvas.pack(side=tk.RIGHT, padx=5)
        
        self.status_var = tk.StringVar()
        self.status_var.set("Готов к работе")
        self.status_bar = ttk.Label(status_frame, textvariable=self.status_var, 
                                   relief=tk.SUNKEN, anchor=tk.W, font=("Arial", 9))
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    def refresh_devices(self):
        """
        Обновляет списки доступных аудио устройств
        """
        if not self.audio_capture:
            return
            
        # Получаем списки устройств
        input_devices = self.audio_capture.list_input_devices()
        output_devices = self.audio_capture.list_output_devices()
        
        # Обновляем выпадающий список устройств ввода
        self.input_device_combobox['values'] = []
        input_device_strings = []
        
        for i, (device_id, name, device_type) in enumerate(input_devices):
            if device_type in ["microphone", "system_sound"]:
                # Микрофоны и системный звук
                input_device_strings.append(f"{device_id}: {name}")
        
        self.input_device_combobox['values'] = input_device_strings
        
        if input_device_strings:
            self.input_device_combobox.current(0)
        
        # Обновляем выпадающий список устройств вывода
        self.output_device_combobox['values'] = []
        output_device_strings = []
        
        for i, (device_id, name, device_type) in enumerate(output_devices):
            if device_type == "output":
                output_device_strings.append(f"{device_id}: {name}")
        
        self.output_device_combobox['values'] = output_device_strings
        
        if output_device_strings:
            self.output_device_combobox.current(0)
            
        # Отображаем информацию о статусе
        self.status_var.set(f"Найдено: {len(input_device_strings)} устройств ввода, {len(output_device_strings)} устройств вывода")
    
    def toggle_recording(self):
        """
        Запускает или останавливает запись
        """
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        """
        Запускает запись и обработку аудио
        """
        if not self.audio_capture or not self.speech_recognizer or not self.chatgpt_client:
            messagebox.showerror("Ошибка", "Не все компоненты инициализированы")
            return
        
        # Получаем индексы выбранных устройств
        try:
            # Устройство ввода
            input_device_str = self.input_device_combobox.get()
            input_device_id_str = input_device_str.split(":")[0].strip()
            input_device_index = int(input_device_id_str)
            
            # Устройство вывода
            output_device_str = self.output_device_combobox.get()
            output_device_id_str = output_device_str.split(":")[0].strip()
            output_device_index = int(output_device_id_str)
            
            # Сохраняем индексы устройств
            self.input_device_index = input_device_index
            self.output_device_index = output_device_index
                
        except (ValueError, IndexError) as e:
            messagebox.showerror("Ошибка", f"Выберите корректные устройства: {e}")
            return
        
        # Проверяем модель распознавания
        current_model = self.model_combobox.get()
        
        # Проверка атрибутов модели Whisper
        try:
            # Получим имя модели более безопасным способом
            model_name = getattr(self.speech_recognizer, 'model_name', None)
            if model_name != current_model:
                self.status_var.set(f"Загрузка модели Whisper {current_model}...")
                self.root.update()
                
                # Создаем новый экземпляр распознавателя с выбранной моделью
                from src.speech_recognition import SpeechRecognizer
                self.speech_recognizer = SpeechRecognizer(model_name=current_model)
        except Exception as e:
            print(f"Ошибка при проверке модели: {e}")
            # Продолжаем с текущей моделью
            pass
        
        # Проверяем модель ChatGPT
        chatgpt_model = self.chatgpt_model_combobox.get()
        if chatgpt_model != self.chatgpt_client.model:
            self.chatgpt_client.model = chatgpt_model
        
        # Запускаем запись
        try:
            # Запускаем запись с обоих устройств
            self.audio_capture.start_recording_with_both(
                input_device_index=self.input_device_index, 
                output_device_index=self.output_device_index
            )
            self.is_recording = True
            
            # Запускаем обработку в отдельном потоке
            self.is_processing = True
            self.processing_thread = threading.Thread(target=self.process_audio)
            self.processing_thread.daemon = True
            self.processing_thread.start()
            
            # Запускаем обновление индикатора аудио
            self.update_audio_level()
            
            # Обновляем UI
            self.start_button.config(text="Остановить запись")
            self.status_var.set(f"Запись и обработка аудио с микрофона и наушников...")
        except Exception as e:
            messagebox.showerror("Ошибка записи", f"Не удалось начать запись: {e}")
            self.is_recording = False
            self.is_processing = False
    
    def stop_recording(self):
        """
        Останавливает запись и обработку аудио
        """
        if self.audio_capture:
            self.audio_capture.stop_recording()
        
        self.is_recording = False
        self.is_processing = False
        
        # Ждем завершения потока обработки
        if hasattr(self, 'processing_thread') and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=1)
        
        # Обновляем UI
        self.start_button.config(text="Начать запись")
        self.status_var.set("Запись остановлена")
    
    def process_audio(self):
        """
        Обрабатывает аудио в отдельном потоке
        """
        while self.is_processing:
            # Получаем следующий сегмент аудио
            frames = self.audio_capture.get_next_audio_segment()
            
            if frames:
                # Преобразуем фреймы в текст
                self.status_var.set("Распознавание речи...")
                language = self.language_combobox.get()
                if language == "auto":
                    language = None
                    
                transcription = self.speech_recognizer.transcribe_audio_data(frames, language=language)
                
                if transcription:
                    # Выводим текст в UI
                    self.update_transcription(transcription)
                    
                    # Отправляем текст в ChatGPT
                    self.status_var.set("Получение ответа от ChatGPT...")
                    response = self.chatgpt_client.get_response(transcription)
                    
                    # Выводим ответ в UI
                    self.update_chat(response)
                    
                    # Обновляем статус
                    self.status_var.set("Готов к обработке следующего фрагмента")
                
                # Сохраняем аудио для отладки (опционально)
                # timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                # self.audio_capture.save_audio(frames, f"audio_{timestamp}.wav")
            
            # Небольшая пауза, чтобы не нагружать процессор
            time.sleep(0.1)
    
    def update_audio_level(self):
        """
        Обновляет индикатор уровня аудио
        """
        if not self.is_recording:
            # Очищаем индикатор
            self.audio_level_canvas.delete("all")
            return
            
        try:
            # Получаем текущий уровень аудио
            level = 0
            if hasattr(self.audio_capture, 'speaking'):
                # Если речь обнаружена, показываем высокий уровень
                if self.audio_capture.speaking:
                    level = 80
                else:
                    # Если речь не обнаружена, но запись идет, показываем низкий уровень
                    level = 20
            
            # Цветовая индикация
            if level < 30:
                color = "blue"
            elif level < 70:
                color = "green"
            else:
                color = "red"
            
            # Обновляем визуализацию
            self.audio_level_canvas.delete("all")
            self.audio_level_canvas.create_rectangle(0, 0, level, 15, fill=color, outline="")
            
            # Планируем следующее обновление
            self.root.after(100, self.update_audio_level)
            
        except Exception as e:
            print(f"Ошибка при обновлении индикатора аудио: {e}")
            # Планируем следующее обновление даже при ошибке
            self.root.after(100, self.update_audio_level)
    
    def update_transcription(self, text):
        """
        Обновляет текст в поле распознавания
        
        Args:
            text (str): Распознанный текст
        """
        # Добавляем временную метку
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_text = f"[{timestamp}] {text}\n\n"
        
        # Вставляем текст в конец
        self.transcription_text.configure(state="normal")
        self.transcription_text.insert(tk.END, formatted_text)
        self.transcription_text.see(tk.END)
        self.transcription_text.configure(state="disabled")
    
    def update_chat(self, text):
        """
        Обновляет текст в поле ответов ChatGPT
        
        Args:
            text (str): Текст ответа
        """
        # Добавляем временную метку
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_text = f"[{timestamp}] {text}\n\n"
        
        # Вставляем текст в конец
        self.chat_text.configure(state="normal")
        self.chat_text.insert(tk.END, formatted_text)
        self.chat_text.see(tk.END)
        self.chat_text.configure(state="disabled")
    
    def generate_summary(self):
        """
        Генерирует и отображает саммари встречи
        """
        if not self.chatgpt_client:
            messagebox.showerror("Ошибка", "ChatGPT клиент не инициализирован")
            return
            
        # Проверяем, есть ли история разговора
        if not self.chatgpt_client.conversation_history:
            messagebox.showinfo("Информация", "История разговора пуста. Нечего резюмировать.")
            return
            
        self.status_var.set("Генерация саммари встречи...")
        self.root.update()
        
        # Генерируем саммари
        summary = self.chatgpt_client.generate_meeting_summary()
        
        # Отображаем саммари
        self.summary_text.configure(state="normal")
        self.summary_text.delete(1.0, tk.END)
        self.summary_text.insert(tk.END, summary)
        self.summary_text.configure(state="disabled")
        
        self.status_var.set("Саммари встречи сгенерировано")
    
    def save_conversation(self):
        """
        Сохраняет историю разговора в файл
        """
        if not self.chatgpt_client:
            messagebox.showerror("Ошибка", "ChatGPT клиент не инициализирован")
            return
            
        # Проверяем, есть ли история разговора
        if not self.chatgpt_client.conversation_history:
            messagebox.showinfo("Информация", "История разговора пуста. Нечего сохранять.")
            return
            
        # Запрашиваем имя файла для сохранения
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")],
            title="Сохранить историю разговора"
        )
        
        if file_path:
            # Сохраняем историю
            filename = self.chatgpt_client.save_conversation(file_path)
            self.status_var.set(f"История разговора сохранена в {filename}")
            
            # Если есть саммари, предлагаем сохранить его отдельно
            if self.summary_text.get(1.0, tk.END).strip():
                if messagebox.askyesno("Сохранить саммари", "Хотите сохранить саммари отдельно в текстовый файл?"):
                    summary_path = filedialog.asksaveasfilename(
                        defaultextension=".txt",
                        filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")],
                        title="Сохранить саммари встречи"
                    )
                    
                    if summary_path:
                        with open(summary_path, 'w', encoding='utf-8') as f:
                            f.write(self.summary_text.get(1.0, tk.END))
                        self.status_var.set(f"Саммари сохранено в {summary_path}")
    
    def load_conversation(self):
        """
        Загружает историю разговора из файла
        """
        if not self.chatgpt_client:
            messagebox.showerror("Ошибка", "ChatGPT клиент не инициализирован")
            return
            
        # Запрашиваем имя файла для загрузки
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")],
            title="Загрузить историю разговора"
        )
        
        if file_path:
            # Очищаем текущую историю
            if self.chatgpt_client.conversation_history and not messagebox.askyesno(
                "Подтверждение", "Текущая история будет перезаписана. Продолжить?"
            ):
                return
                
            # Загружаем историю
            if self.chatgpt_client.load_conversation(file_path):
                self.status_var.set(f"История разговора загружена из {file_path}")
                
                # Очищаем текущие поля
                self.transcription_text.configure(state="normal")
                self.transcription_text.delete(1.0, tk.END)
                
                self.chat_text.configure(state="normal")
                self.chat_text.delete(1.0, tk.END)
                
                # Отображаем загруженную историю
                for message in self.chatgpt_client.conversation_history:
                    if message["role"] == "user":
                        self.update_transcription(message["content"])
                    elif message["role"] == "assistant":
                        self.update_chat(message["content"])
                
                # Предлагаем сгенерировать саммари
                if messagebox.askyesno("Генерация саммари", "Хотите сгенерировать саммари для загруженной истории?"):
                    self.generate_summary()
            else:
                messagebox.showerror("Ошибка", "Не удалось загрузить историю разговора")
    
    def clear_history(self):
        """
        Очищает историю разговора и все текстовые поля
        """
        if not self.chatgpt_client:
            messagebox.showerror("Ошибка", "ChatGPT клиент не инициализирован")
            return
            
        # Подтверждение
        if not messagebox.askyesno("Подтверждение", "Вы уверены, что хотите очистить всю историю разговора?"):
            return
            
        # Очищаем историю в ChatGPT клиенте
        self.chatgpt_client.clear_conversation()
        
        # Очищаем текстовые поля
        self.transcription_text.configure(state="normal")
        self.transcription_text.delete(1.0, tk.END)
        self.transcription_text.configure(state="disabled")
        
        self.chat_text.configure(state="normal")
        self.chat_text.delete(1.0, tk.END)
        self.chat_text.configure(state="disabled")
        
        self.summary_text.configure(state="normal")
        self.summary_text.delete(1.0, tk.END)
        self.summary_text.configure(state="disabled")
        
        self.status_var.set("История разговора очищена")
    
    def on_closing(self):
        """
        Обработчик закрытия окна
        """
        # Останавливаем запись, если она активна
        if self.is_recording:
            self.stop_recording()
        
        # Если есть несохраненная история, предлагаем сохранить
        if self.chatgpt_client and self.chatgpt_client.conversation_history:
            if messagebox.askyesno("Сохранение", "Сохранить историю разговора перед выходом?"):
                self.save_conversation()
        
        # Закрываем аудио ресурсы
        if self.audio_capture:
            self.audio_capture.close()
        
        # Закрываем окно
        self.root.destroy()


# Тестовый код (выполняется только при запуске файла напрямую)
if __name__ == "__main__":
    from src.audio_capture import AudioCapture
    from src.speech_recognition import SpeechRecognizer
    from src.chatgpt_client import ChatGPTClient
    
    # Создаем корневое окно
    root = tk.Tk()
    
    try:
        # Инициализируем компоненты
        audio_capture = AudioCapture()
        
        # Для теста используем маленькую модель, чтобы быстрее загружалась
        speech_recognizer = SpeechRecognizer(model_name="tiny")
        
        # Для теста без API ключа можно использовать заглушку
        try:
            chatgpt_client = ChatGPTClient()
        except ValueError:
            # Если API ключ не найден, используем заглушку
            class DummyChatGPTClient:
                def __init__(self):
                    self.model = "gpt-3.5-turbo"
                    self.conversation_history = []
                
                def add_message(self, content, role="user"):
                    self.conversation_history.append({"role": role, "content": content})

                def get_response(self, prompt=None):
                    if prompt:
                        self.add_message(prompt)
                    response = f"Это тестовый ответ на запрос: {prompt}"
                    self.add_message(response, role="assistant")
                    return response
                
                def generate_meeting_summary(self):
                    return "Тестовое саммари встречи"
                
                def save_conversation(self, filename=None):
                    if filename is None:
                        filename = "test_conversation.json"
                    print(f"Сохранение в {filename}")
                    return filename
                
                def load_conversation(self, filename):
                    print(f"Загрузка из {filename}")
                    self.conversation_history = [
                        {"role": "user", "content": "Тестовый запрос 1"},
                        {"role": "assistant", "content": "Тестовый ответ 1"}
                    ]
                    return True
                
                def clear_conversation(self):
                    self.conversation_history = []
            
            chatgpt_client = DummyChatGPTClient()
            print("Внимание: Используется заглушка ChatGPT клиента. Установите API ключ для полной функциональности.")
        
        # Создаем интерфейс
        ui = AudioAssistantUI(root, audio_capture, speech_recognizer, chatgpt_client)
        
        # Запускаем главный цикл
        root.mainloop()
        
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка при инициализации: {str(e)}")
        root.destroy()
