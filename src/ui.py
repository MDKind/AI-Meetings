import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
import threading
import time
import datetime
from utils.config import UI_SETTINGS, CHATGPT_SETTINGS

class AudioAssistantUI:
    """
    Класс для создания пользовательского интерфейса аудио-ассистента
    """
    def __init__(self, root, audio_capture=None, speech_recognizer=None, chatgpt_client=None,
                 realtime_assistant=None, env_path=None):
        """
        Инициализирует пользовательский интерфейс
        
        Args:
            root: Корневой элемент Tkinter
            audio_capture: Экземпляр класса AudioCapture
            speech_recognizer: Экземпляр класса SpeechRecognizer
            chatgpt_client: Экземпляр класса ChatGPTClient
            realtime_processor: Экземпляр класса RealTimeAudioProcessor
            realtime_assistant: Экземпляр класса RealtimeMeetingAssistant
        """
        self.root = root
        self.root.title(UI_SETTINGS['window_title'])
        self.root.geometry(UI_SETTINGS['window_size'])
        
        # Устанавливаем компоненты
        self.audio_capture = audio_capture
        self.speech_recognizer = speech_recognizer
        self.chatgpt_client = chatgpt_client
        self.realtime_assistant = realtime_assistant
        self.env_path = env_path  # путь к .env для сохранения настроек
        
        # Флаги состояния
        self.is_recording = False
        self.is_processing = False
        self.input_device_index = None
        self.output_device_index = None
        self.assistant_active = False
        
        # Буфер накопленных транскрипций (не отправляем в LLM автоматически)
        self.transcription_buffer = []

        # Создаем пользовательский интерфейс
        self.create_ui()

        # Инициализируем список устройств
        self.refresh_devices()

        # Если base_url уже задан в .env — подгружаем модели с сервера при старте
        if self._get_default_api_base_url():
            self.root.after(500, self.apply_api_settings)

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
        
        ttk.Label(settings_frame, text="Модель LLM:", font=default_font).grid(row=0, column=4, padx=(15, 5), pady=5, sticky="w")
        # Если задан base_url — комбобокс будет заполнен из сервера после подключения.
        # Если нет — показываем стандартные OpenAI модели.
        _has_base_url = bool(CHATGPT_SETTINGS.get('api_base_url', ''))
        _initial_llm_values = [] if _has_base_url else ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
        self.chatgpt_model_combobox = ttk.Combobox(
            settings_frame,
            values=_initial_llm_values,
            width=22, font=default_font
        )
        if not _has_base_url:
            default_model = CHATGPT_SETTINGS.get('default_model', 'gpt-4o')
            self.chatgpt_model_combobox.set(default_model)
        self.chatgpt_model_combobox.grid(row=0, column=5, padx=5, pady=5, sticky="w")

        # Строка настроек API
        api_frame = ttk.Frame(control_frame)
        api_frame.pack(fill="x", pady=2)

        ttk.Label(api_frame, text="API Base URL:", font=default_font).pack(side="left", padx=5)
        self.api_base_url_var = tk.StringVar(value=self._get_default_api_base_url())
        self.api_base_url_entry = ttk.Entry(api_frame, textvariable=self.api_base_url_var,
                                            width=40, font=default_font)
        self.api_base_url_entry.pack(side="left", padx=5)
        ttk.Label(api_frame, text="(пусто = OpenAI)", font=("Arial", 8)).pack(side="left")
        ttk.Button(api_frame, text="Применить", command=self.apply_api_settings,
                   width=10).pack(side="left", padx=5)
        self.api_status_label = ttk.Label(api_frame, text="", font=("Arial", 8), foreground="green")
        self.api_status_label.pack(side="left", padx=5)
        
        # Кнопки управления
        buttons_frame = ttk.Frame(control_frame)
        buttons_frame.pack(fill="x", pady=5)
        
        self.start_button = ttk.Button(buttons_frame, text="Начать запись", 
                                      command=self.toggle_recording, width=15)
        self.start_button.pack(side="left", padx=5)
        
        ttk.Button(buttons_frame, text="Сгенерировать саммари",
                  command=self.generate_summary, width=20).pack(side="left", padx=5)

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
        
    def _get_default_api_base_url(self):
        """Возвращает значение API base URL из конфига или пустую строку."""
        from utils.config import CHATGPT_SETTINGS
        return CHATGPT_SETTINGS.get('api_base_url', '') or ''

    def _save_env(self, api_key, api_base, model):
        """Сохраняет настройки API в .env файл."""
        if not self.env_path:
            return
        lines = []
        try:
            with open(self.env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            pass

        def _set(key, value):
            """Обновляет или добавляет строку key=value, раскомментируя при необходимости."""
            found = False
            for i, line in enumerate(lines):
                stripped = line.lstrip('# \t')
                if stripped.startswith(key + '='):
                    lines[i] = f'{key}={value}\n' if value else f'# {key}=\n'
                    found = True
                    break
            if not found:
                if value:
                    lines.append(f'{key}={value}\n')

        if api_key is not None:  # None = не трогать существующий ключ
            _set('OPENAI_API_KEY', api_key)
        _set('OPENAI_API_BASE', api_base or '')
        _set('CHATGPT_MODEL', model or '')

        try:
            with open(self.env_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        except Exception as e:
            print(f"Не удалось сохранить .env: {e}")

    def apply_api_settings(self):
        """
        Применяет новые настройки API (base URL и модель) к ChatGPT клиенту без перезапуска.
        Автоматически определяет тип API (OpenAI / LM Studio Runtime).
        Загрузка моделей выполняется в фоновом потоке.
        Сохраняет настройки в .env.
        """
        if not self.chatgpt_client:
            return

        from src.chatgpt_client import _is_lmstudio_runtime

        base_url = self.api_base_url_var.get().strip() or None
        model = self.chatgpt_model_combobox.get().strip()

        try:
            # Обновляем параметры существующего клиента (не пересоздаём — история сохраняется)
            self.chatgpt_client.base_url = base_url
            self.chatgpt_client._lmstudio_runtime = _is_lmstudio_runtime(base_url)
            if model:
                self.chatgpt_client.model = model

            # Если переключились на LM Studio Runtime — пересоздаём внутренний OpenAI client
            # (или убираем его если он уже не нужен)
            if self.chatgpt_client._lmstudio_runtime:
                self.chatgpt_client.client = None
            else:
                from openai import OpenAI
                api_key = self.chatgpt_client.api_key or "local"
                kw = {'api_key': api_key}
                if base_url:
                    kw['base_url'] = base_url
                self.chatgpt_client.client = OpenAI(**kw)

            # Сохраняем в .env сразу
            self._save_env(api_key=None, api_base=base_url or '', model=model or '')

            # Статус
            if base_url:
                mode = "LM Studio Runtime" if _is_lmstudio_runtime(base_url) else "OpenAI-compatible"
                self.api_status_label.config(text=f"✓ {base_url} ({mode})", foreground="green")
            else:
                self.api_status_label.config(text="✓ OpenAI API", foreground="green")

            # Загружаем модели с сервера в фоне
            if base_url:
                threading.Thread(target=self._fetch_models, args=(base_url,), daemon=True).start()

        except Exception as e:
            self.api_status_label.config(text=f"Ошибка: {e}", foreground="red")

    def _fetch_models(self, base_url):
        """Загружает список моделей с сервера в фоновом потоке и обновляет комбобокс."""
        import requests as _requests
        try:
            models_url = base_url.rstrip('/') + '/models'
            resp = _requests.get(models_url, timeout=5)
            print(f"Fetch models: {models_url} -> {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"Models response keys: {list(data.keys())}")
                # OpenAI/LM Studio: {"data": [{"id": "..."}]}
                model_ids = [m['id'] for m in data.get('data', []) if 'id' in m]
                # LM Studio Runtime может вернуть {"models": [...]} или просто список
                if not model_ids and 'models' in data:
                    model_ids = [m.get('id') or m.get('name') for m in data['models'] if isinstance(m, dict)]
                    model_ids = [m for m in model_ids if m]
                if not model_ids and isinstance(data, list):
                    model_ids = [m.get('id') or m.get('name') for m in data if isinstance(m, dict)]
                    model_ids = [m for m in model_ids if m]
                model_ids = sorted(model_ids)
                print(f"Found models: {model_ids}")
                if model_ids:
                    self.root.after(0, self._update_model_combobox, model_ids)
        except Exception as e:
            print(f"Ошибка загрузки моделей: {e}")

    def _update_model_combobox(self, model_ids):
        """Обновляет комбобокс моделей в главном потоке."""
        current = self.chatgpt_model_combobox.get()
        self.chatgpt_model_combobox['values'] = model_ids
        if current not in model_ids:
            self.chatgpt_model_combobox.set(model_ids[0])
            if self.chatgpt_client:
                self.chatgpt_client.model = model_ids[0]
            # Сохраняем обновлённую модель
            self._save_env(api_key=None, api_base=self.chatgpt_client.base_url or '', model=model_ids[0])

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
        Запускает запись и обработку аудио с использованием выбранного режима
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
        
        try:
            self.audio_capture.start_enhanced_recording(
                input_device_index=self.input_device_index,
                output_device_index=self.output_device_index
            )

            self.is_recording = True
            if self.realtime_assistant:
                self.assistant_active = True

            # Запускаем обработку в отдельном потоке
            self.is_processing = True
            self.processing_thread = threading.Thread(target=self.process_audio)
            self.processing_thread.daemon = True
            self.processing_thread.start()
            
            # Запускаем обновление индикатора аудио
            self.update_audio_level()
            
            # Обновляем UI
            self.start_button.config(text="Остановить запись")
            self.status_var.set("Запись и обработка аудио...")
        except Exception as e:
            messagebox.showerror("Ошибка записи", f"Не удалось начать запись: {e}")
            self.is_recording = False
            self.is_processing = False

    def show_error(self, error_message):
        """
        Отображает сообщение об ошибке
        
        Args:
            error_message (str): Текст сообщения об ошибке
        """
        messagebox.showerror("Ошибка", error_message)
        self.status_var.set(f"Ошибка: {error_message}")
    
    def stop_recording(self):
        """
        Останавливает запись и обработку аудио
        """
        # Если используется ассистент реального времени
        if self.assistant_active and self.realtime_assistant:
            self.realtime_assistant.stop()
            self.assistant_active = False
        
        # Стандартная остановка
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
        
        # Если использовался ассистент, предлагаем сгенерировать саммари
        if self.assistant_active and self.realtime_assistant:
            if messagebox.askyesno("Саммари встречи", "Хотите сгенерировать саммари встречи?"):
                self.generate_summary_with_assistant()
    
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
            
            # Отображаем разные цвета для разных устройств
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
            
    def update_transcription(self, text, speaker="local", start_time=None):
        """
        Обновляет текст в поле распознавания с цветовой индикацией говорящего.

        Args:
            text (str): Распознанный текст
            speaker (str): "local" (я) или "remote" (собеседник)
            start_time (datetime, optional): Время начала сегмента
        """
        ts = start_time.strftime("%H:%M:%S") if start_time else datetime.datetime.now().strftime("%H:%M:%S")
        speaker_label = "Я" if speaker == "local" else "Собеседник"
        tag = f"speaker_{speaker}"

        self.transcription_text.configure(state="normal")

        # Настраиваем теги цветов один раз при первом использовании
        if not hasattr(self, '_tags_configured'):
            self.transcription_text.tag_configure(
                "speaker_local",
                foreground="#1a56db",   # синий — ваш голос
                font=("Arial", UI_SETTINGS['font_size'], "bold")
            )
            self.transcription_text.tag_configure(
                "speaker_remote",
                foreground="#057a55",   # зелёный — собеседник
                font=("Arial", UI_SETTINGS['font_size'], "bold")
            )
            self._tags_configured = True

        # Заголовок реплики (с цветом)
        header = f"[{ts}] {speaker_label}: "
        self.transcription_text.insert(tk.END, header, tag)
        # Текст реплики (обычный)
        self.transcription_text.insert(tk.END, f"{text}\n\n")

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
        Генерирует и отображает саммари встречи по накопленным транскрипциям.
        Вызывается явно по кнопке — не в реальном времени.
        """
        if not self.chatgpt_client:
            messagebox.showerror("Ошибка", "ChatGPT клиент не инициализирован")
            return

        if not self.chatgpt_client.conversation_history and not self.transcription_buffer:
            messagebox.showinfo("Информация", "Нет записанных фрагментов. Начните запись.")
            return

        self.status_var.set("Генерация саммари встречи...")
        self.root.update()

        # Генерируем саммари в фоновом потоке, чтобы не блокировать UI
        def _do_summary():
            from utils.storage import storage
            summary_text = self.chatgpt_client.generate_meeting_summary()
            # Сохраняем в storage
            try:
                summary_dict = {
                    "title": getattr(self, '_meeting_title', None),
                    "date": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "duration_seconds": 0,
                    "summary": summary_text,
                    "transcript": [
                        {"role": m["role"], "content": m["content"],
                         "speaker": m.get("speaker", "unknown"),
                         "timestamp": m.get("timestamp", "")}
                        for m in self.chatgpt_client.conversation_history
                    ],
                }
                storage.save_summary(summary_dict)
            except Exception as e:
                print(f"Storage: не удалось сохранить саммари: {e}")
            self.root.after(0, self._show_summary, summary_text)

        threading.Thread(target=_do_summary, daemon=True).start()

    def _show_summary(self, summary):
        """Отображает готовое саммари в UI (вызывается из main thread)."""
        self.summary_text.configure(state="normal")
        self.summary_text.delete(1.0, tk.END)
        self.summary_text.insert(tk.END, summary)
        self.summary_text.configure(state="disabled")
        self.status_var.set("Саммари встречи сгенерировано")
        # Очищаем буфер после сохранения саммари
        self.transcription_buffer = []
    
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
            
        # Очищаем историю в ChatGPT клиенте и локальный буфер
        self.chatgpt_client.clear_conversation()
        self.transcription_buffer = []
        
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
    
    def generate_summary_with_assistant(self):
        """
        Генерирует саммари встречи через ассистента реального времени (в фоновом потоке).
        """
        if not self.realtime_assistant:
            self.generate_summary()
            return

        self.status_var.set("Генерация саммари встречи через ассистента...")

        def _do():
            summary = self.realtime_assistant.generate_meeting_summary()
            self.root.after(0, self._show_summary, summary)
            self.root.after(0, lambda: self.status_var.set("Саммари встречи сгенерировано через ассистента"))

        threading.Thread(target=_do, daemon=True).start()
    
    def process_audio(self):
        """
        Обрабатывает аудио в отдельном потоке.
        Распознаёт речь и накапливает транскрипции в буфер.
        ChatGPT вызывается только явно — по кнопке «Сгенерировать саммари».
        """
        while self.is_processing:
            segment = self.audio_capture.get_next_audio_segment()

            if segment:
                # segment — dict: {"frames", "speaker", "start_time", "end_time"}
                frames = segment.get("frames", segment) if isinstance(segment, dict) else segment
                speaker = segment.get("speaker", "local") if isinstance(segment, dict) else "local"
                start_time = segment.get("start_time") if isinstance(segment, dict) else None

                self.status_var.set("Распознавание речи...")
                language = self.language_combobox.get()
                if language == "auto":
                    language = None

                transcription = self.speech_recognizer.transcribe_audio_data(frames, language=language)

                if transcription:
                    # Формируем метку говорящего
                    speaker_label = "Я" if speaker == "local" else "Собеседник"

                    # Добавляем в ChatGPT историю с пометкой говорящего и speaker
                    msg_content = f"[{speaker_label}]: {transcription}"
                    self.chatgpt_client.add_message(msg_content, role="user", speaker=speaker)

                    # Накапливаем в локальный буфер
                    self.transcription_buffer.append({
                        "text": transcription,
                        "speaker": speaker,
                        "speaker_label": speaker_label,
                        "start_time": start_time,
                    })

                    # Выводим в UI с пометкой говорящего
                    self.root.after(0, self.update_transcription, transcription, speaker, start_time)

                    self.status_var.set(f"Записано фрагментов: {len(self.transcription_buffer)}")

            time.sleep(0.1)
    
    def on_closing(self):
        """
        Обработчик закрытия окна
        """
        # Останавливаем запись, если она активна
        if self.is_recording:
            self.stop_recording()
        
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