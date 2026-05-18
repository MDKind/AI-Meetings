import flet as ft
import os
import datetime
import threading
import time

from utils.config import UI_SETTINGS, CHATGPT_SETTINGS

class FletAudioAssistantUI:
    def __init__(self, page: ft.Page, audio_capture=None, speech_recognizer=None, 
                 chatgpt_client=None, realtime_assistant=None, env_path=None):
        self.page = page
        self.audio_capture = audio_capture
        self.speech_recognizer = speech_recognizer
        self.chatgpt_client = chatgpt_client
        self.realtime_assistant = realtime_assistant
        self.env_path = env_path

        self.is_recording = False
        self.is_processing = False
        self.assistant_active = False
        self.postprocess_enabled = False

        self.transcription_buffer = []
        self._transcript_entries: list = []

        def get_version():
            import sys
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            try:
                return open(os.path.join(base_path, 'version.txt')).read().strip()
            except:
                return "1.0.0"

        def find_icon():
            import sys
            candidates = [
                os.path.join(os.path.dirname(sys.executable), 'icon.ico'),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'installer', 'assets', 'icon.ico'),
            ]
            return next((p for p in candidates if os.path.exists(p)), None)

        self.version = get_version()
        self.page.title = f"{UI_SETTINGS['window_title']} v{self.version}"
        icon_path = find_icon()
        if icon_path:
            self.page.icon = icon_path
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.width = UI_SETTINGS['window_width']
        self.page.window.height = UI_SETTINGS['window_height']
        self.page.padding = 0
        self.page.fonts = {
            "Inter": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
        }
        self.page.theme = ft.Theme(font_family="Inter")

        self.setup_ui()
        self.refresh_devices()

    def refresh_devices(self, e=None):
        if not self.audio_capture: return
        input_devices = self.audio_capture.list_input_devices()
        output_devices = self.audio_capture.list_output_devices()

        self.dd_input.options = [ft.dropdown.Option(f"{idx}: {name}") for idx, name, _ in input_devices]
        self.dd_output.options = [ft.dropdown.Option(f"{idx}: {name}") for idx, name, _ in output_devices]

        default_in = next((f"{idx}: {name}" for idx, name, _ in input_devices if "[по умолчанию]" in name), None)
        default_out = next((f"{idx}: {name}" for idx, name, _ in output_devices if "[по умолчанию]" in name), None)

        if default_in: self.dd_input.value = default_in
        elif input_devices: self.dd_input.value = f"{input_devices[0][0]}: {input_devices[0][1]}"
        
        if default_out: self.dd_output.value = default_out
        elif output_devices: self.dd_output.value = f"{output_devices[0][0]}: {output_devices[0][1]}"
        
        self.page.update()

    def start_recording(self):
        if not self.audio_capture or not self.speech_recognizer:
            self.show_snack("Ошибка: компоненты не инициализированы", ft.colors.RED_400)
            return

        try:
            in_idx = int(self.dd_input.value.split(":")[0])
            out_idx = int(self.dd_output.value.split(":")[0])
        except Exception:
            self.show_snack("Ошибка выбора устройств", ft.colors.RED_400)
            return

        # Update language/model settings
        lang = self.dd_language.value
        if lang == "auto": lang = None

        if self.chatgpt_client:
            self.chatgpt_client.model = self.dd_llm.value

        try:
            self._transcript_entries = []
            self.audio_capture.start_enhanced_recording(input_device_index=in_idx, output_device_index=out_idx)
            self.is_recording = True
            self.is_processing = True
            
            # Start processing thread
            self.processing_thread = threading.Thread(target=self.process_audio, daemon=True)
            self.processing_thread.start()

            # Update UI
            self.btn_record.icon = ft.icons.STOP_ROUNDED
            self.btn_record.text = "Остановить"
            self.btn_record.bgcolor = ft.colors.RED_700
            self.status_text.value = "Идёт запись..."
            self.pulse_ring.visible = True
            self.page.update()
            
        except Exception as e:
            self.show_snack(f"Ошибка записи: {e}", ft.colors.RED_400)

    def stop_recording(self):
        if self.audio_capture:
            self.audio_capture.stop_recording()
        
        self.is_recording = False
        self.is_processing = False

        self.btn_record.icon = ft.icons.FIBER_MANUAL_RECORD_ROUNDED
        self.btn_record.text = "Запись"
        self.btn_record.bgcolor = ft.colors.BLUE_700
        self.status_text.value = "Запись остановлена"
        self.pulse_ring.visible = False
        self.page.update()
        self._try_diarize()

    def toggle_record(self, e):
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def process_audio(self):
        while self.is_processing:
            segment = self.audio_capture.get_next_audio_segment()
            if segment:
                frames = segment.get("frames", segment) if isinstance(segment, dict) else segment
                speaker = segment.get("speaker", "local") if isinstance(segment, dict) else "local"
                
                lang = self.dd_language.value
                if lang == "auto": lang = None
                
                transcription = self.speech_recognizer.transcribe_audio_data(frames, language=lang)
                if transcription:
                    polished = False
                    if self.postprocess_enabled and self.chatgpt_client:
                        try:
                            improved = self.chatgpt_client.polish_transcription(transcription)
                            if improved and improved.strip() != transcription.strip():
                                transcription = improved
                                polished = True
                        except Exception:
                            pass
                    self.append_transcription(transcription, speaker, polished=polished,
                                              start_time=segment.get("start_time"))
            time.sleep(0.1)

    def append_transcription(self, text, speaker, polished=False, start_time=None):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        is_local = speaker == "local"
        speaker_name = "Я" if is_local else "Собеседник"
        color = ft.colors.BLUE_400 if is_local else ft.colors.GREEN_400

        self.transcription_buffer.append({"text": text, "speaker": speaker_name})

        if self.chatgpt_client:
            self.chatgpt_client.add_message(f"[{speaker_name}]: {text}", role="user")

        start_offset = None
        if is_local and start_time is not None and self.audio_capture and self.audio_capture.session_start:
            start_offset = max(0.0, (start_time - self.audio_capture.session_start).total_seconds())

        speaker_ctrl = ft.Text(speaker_name, color=color, size=12, weight=ft.FontWeight.BOLD)
        self._transcript_entries.append({
            "start_offset": start_offset,
            "speaker_raw": speaker,
            "speaker_ctrl": speaker_ctrl,
        })

        header_row = ft.Row([
            speaker_ctrl,
            ft.Text(f" • {ts}", color=ft.colors.GREY_500, size=12),
            *(
                [ft.Icon(ft.icons.AUTO_AWESOME, size=12, color=ft.colors.AMBER_400,
                         tooltip="Улучшено LLM")]
                if polished else []
            ),
        ], spacing=4)

        msg = ft.Container(
            content=ft.Column([header_row, ft.Text(text, size=14)], spacing=2),
            bgcolor=ft.colors.SURFACE_VARIANT,
            padding=10,
            border_radius=8,
            margin=ft.margin.only(bottom=10, left=0 if is_local else 40, right=40 if is_local else 0)
        )
        self.transcript_view.controls.append(msg)
        self.page.update()
        self.transcript_view.scroll_to(offset=-1, duration=200)

    def generate_summary(self, e):
        if not self.chatgpt_client or not self.transcription_buffer:
            self.show_snack("Нет данных для саммари", ft.colors.ORANGE_400)
            return

        self.status_text.value = "Генерация саммари..."
        self.pr_summary.visible = True
        self.page.update()

        def _do():
            try:
                summary = self.chatgpt_client.generate_meeting_summary()
                self.summary_text.value = summary
                self.status_text.value = "Саммари готово"
                # Select summary tab
                self.tabs.selected_index = 1
            except Exception as ex:
                self.show_snack(f"Ошибка LLM: {ex}", ft.colors.RED_400)
                self.status_text.value = "Ошибка генерации"
            finally:
                self.pr_summary.visible = False
                self.page.update()

        threading.Thread(target=_do, daemon=True).start()

    def clear_history(self, e):
        self.transcription_buffer = []
        self._transcript_entries = []
        if self.chatgpt_client:
            self.chatgpt_client.clear_conversation()
        self.transcript_view.controls.clear()
        self.summary_text.value = ""
        self.status_text.value = "История очищена"
        self.page.update()

    def _try_diarize(self):
        try:
            from src import diarization as diar
        except ImportError:
            return
        if not diar.is_available():
            return
        if not self.audio_capture:
            return
        pcm = self.audio_capture.session_pcm
        if len(pcm) < 2 * 16000 * 2:
            return
        entries_snapshot = [e for e in self._transcript_entries if e["speaker_raw"] == "local"]
        if not entries_snapshot:
            return

        def _run():
            try:
                def status_cb(msg):
                    self.status_text.value = msg
                    self.page.update()
                status_cb("Диаризация...")
                segments = diar.diarize(pcm, status_cb=status_cb)
                self._apply_diarization(segments, entries_snapshot)
            except Exception as e:
                print(f"[Diarization] Ошибка: {e}")
            finally:
                self.status_text.value = "Запись остановлена"
                self.page.update()

        threading.Thread(target=_run, daemon=True).start()

    _DIAR_COLORS = [
        ft.colors.BLUE_400,
        ft.colors.ORANGE_400,
        ft.colors.PURPLE_400,
        ft.colors.TEAL_400,
    ]

    def _apply_diarization(self, segments, entries):
        speaker_map: dict = {}

        for entry in entries:
            offset = entry["start_offset"]
            if offset is None:
                continue
            matched = next(
                (s for s in segments if s.start <= offset < s.end),
                None,
            )
            if matched is None and segments:
                matched = min(segments, key=lambda s: abs((s.start + s.end) / 2 - offset))
            if matched is None:
                continue
            sid = matched.speaker_id
            if sid not in speaker_map:
                n = len(speaker_map) + 1
                speaker_map[sid] = (f"Участник {n}", self._DIAR_COLORS[(n - 1) % len(self._DIAR_COLORS)])
            label, color = speaker_map[sid]
            entry["speaker_ctrl"].value = label
            entry["speaker_ctrl"].color = color

        if len(speaker_map) <= 1:
            for entry in entries:
                entry["speaker_ctrl"].value = "Я"
                entry["speaker_ctrl"].color = ft.colors.BLUE_400

        self.page.update()

    def show_snack(self, text, color):
        self.page.snack_bar = ft.SnackBar(ft.Text(text), bgcolor=color)
        self.page.snack_bar.open = True
        self.page.update()

    def apply_api_settings(self, e=None):
        if not self.chatgpt_client: return
        api_key = self.tb_api_key.value.strip()
        base_url = self.tb_base_url.value.strip()
        model = self.dd_llm.value

        self.chatgpt_client.base_url = base_url or None
        if api_key:
            self.chatgpt_client.api_key = api_key
        self.chatgpt_client.model = model
        self.chatgpt_client._reinit_client()

        self.postprocess_enabled = self.sw_postprocess.value

        if self.env_path:
            self._save_env(api_key, base_url, model)

        self.show_snack("Настройки применены", ft.colors.GREEN_600)

    def _save_env(self, api_key: str, base_url: str, model: str, whisper_model: str = None):
        """Сохраняет настройки в .env файл."""
        import re
        try:
            try:
                with open(self.env_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except FileNotFoundError:
                lines = []

            def set_var(lines, key, value):
                pattern = re.compile(rf'^{re.escape(key)}\s*=.*$', re.MULTILINE)
                entry = f'{key}={value}\n'
                for i, line in enumerate(lines):
                    if pattern.match(line):
                        lines[i] = entry
                        return lines
                lines.append(entry)
                return lines

            if api_key:
                lines = set_var(lines, 'OPENAI_API_KEY', api_key)
            if base_url:
                lines = set_var(lines, 'OPENAI_API_BASE', base_url)
            if model:
                lines = set_var(lines, 'CHATGPT_MODEL', model)
            if whisper_model:
                lines = set_var(lines, 'WHISPER_MODEL', whisper_model)

            os.makedirs(os.path.dirname(self.env_path), exist_ok=True)
            with open(self.env_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        except Exception as ex:
            print(f"[Settings] Не удалось сохранить .env: {ex}")

    def _open_settings(self, e=None):
        if self.chatgpt_client:
            key = self.chatgpt_client.api_key or ''
            if key == 'local':
                key = ''
            self.tb_api_key.value = key
            self.tb_base_url.value = self.chatgpt_client.base_url or ''
            self.dd_llm.value = self.chatgpt_client.model
        self.sw_postprocess.value = self.postprocess_enabled
        self.settings_dlg.open = True
        self.page.update()

    def _fetch_llm_models(self, e=None):
        if not self.chatgpt_client: return
        base_url = self.tb_base_url.value.strip() or None
        api_key = self.tb_api_key.value.strip() or None

        def _do():
            try:
                models = self.chatgpt_client.fetch_available_models(base_url=base_url, api_key=api_key)
                if models:
                    self.dd_llm.options = [ft.dropdown.Option(m) for m in models]
                    if self.dd_llm.value not in models:
                        self.dd_llm.value = models[0]
                    self.page.update()
                    self.show_snack(f"Загружено {len(models)} моделей", ft.colors.GREEN_600)
                else:
                    self.show_snack("Нет доступных моделей", ft.colors.ORANGE_400)
            except Exception as ex:
                self.show_snack(f"Ошибка загрузки моделей: {ex}", ft.colors.RED_400)

        threading.Thread(target=_do, daemon=True).start()

    def _change_whisper_model(self, e):
        if not self.speech_recognizer: return
        model_name = e.control.value
        if not model_name or model_name == self.speech_recognizer.model_name: return

        self.btn_record.disabled = True
        self.status_text.value = f"Загрузка модели {model_name}..."
        self.page.update()

        def _do():
            try:
                self.speech_recognizer.set_model(model_name)
                self.status_text.value = f"Модель {model_name} готова"
                if self.env_path:
                    self._save_env('', '', '', whisper_model=model_name)
            except Exception as ex:
                self.status_text.value = "Ошибка загрузки модели"
                self.show_snack(f"Ошибка загрузки модели: {ex}", ft.colors.RED_400)
            finally:
                self.btn_record.disabled = False
                self.page.update()

        threading.Thread(target=_do, daemon=True).start()

    def setup_ui(self):
        # Top App Bar
        self.page.appbar = ft.AppBar(
            title=ft.Text(f"AI Meetings v{self.version}", weight=ft.FontWeight.BOLD),
            center_title=False,
            bgcolor=ft.colors.SURFACE_VARIANT,
            actions=[
                ft.IconButton(ft.icons.SETTINGS, on_click=self._open_settings),
                ft.Container(width=10)
            ]
        )

        # Settings Dialog
        self.tb_api_key = ft.TextField(label="API Key (OpenAI)", password=True, can_reveal_password=True)
        self.tb_base_url = ft.TextField(label="Base URL (пусто = OpenAI; LM Studio: http://127.0.0.1:1234/v1)")
        self.dd_llm = ft.Dropdown(
            label="LLM Model",
            options=[
                ft.dropdown.Option("gpt-4o"),
                ft.dropdown.Option("gpt-4-turbo"),
                ft.dropdown.Option("gpt-3.5-turbo"),
            ],
            value=CHATGPT_SETTINGS.get('default_model', 'gpt-4o'),
            expand=True,
        )
        self.sw_postprocess = ft.Switch(
            label="LLM-улучшение качества",
            value=False,
            tooltip="Улучшать каждый фрагмент транскрипта через LLM: исправляет ошибки распознавания, пунктуацию, делает текст связным. Добавляет задержку на каждый фрагмент.",
        )

        self.settings_dlg = ft.AlertDialog(
            title=ft.Text("Настройки"),
            content=ft.Container(
                width=420,
                content=ft.Column([
                    self.tb_api_key,
                    self.tb_base_url,
                    ft.Row([
                        self.dd_llm,
                        ft.IconButton(
                            ft.icons.SYNC,
                            tooltip="Загрузить список моделей с сервера",
                            on_click=self._fetch_llm_models,
                        ),
                    ], vertical_alignment=ft.CrossAxisAlignment.END),
                    ft.Divider(),
                    self.sw_postprocess,
                ], tight=True, spacing=8),
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: [setattr(self.settings_dlg, 'open', False), self.page.update()]),
                ft.TextButton("Применить", on_click=lambda e: [self.apply_api_settings(), setattr(self.settings_dlg, 'open', False), self.page.update()]),
            ],
        )
        self.page.overlay.append(self.settings_dlg)

        # Sidebar (Devices & Controls)
        self.dd_input = ft.Dropdown(label="Микрофон", text_size=13)
        self.dd_output = ft.Dropdown(label="Системный звук (Динамики)", text_size=13)
        self.dd_language = ft.Dropdown(label="Язык", options=[
            ft.dropdown.Option("ru"), ft.dropdown.Option("en"), ft.dropdown.Option("auto")
        ], value="ru", text_size=13)

        _cur_model = getattr(self.speech_recognizer, 'model_name', 'base') if self.speech_recognizer else 'base'
        self.dd_whisper = ft.Dropdown(
            label="Модель Whisper",
            options=[
                ft.dropdown.Option(key="tiny", text="tiny (~75 MB, быстрая)"),
                ft.dropdown.Option(key="base", text="base (~142 MB)"),
                ft.dropdown.Option(key="small", text="small (~466 MB, лучше)"),
                ft.dropdown.Option(key="medium", text="medium (~1.5 GB, хорошая)"),
                ft.dropdown.Option(key="large-v3-turbo", text="large-v3-turbo (~1.6 GB)"),
                ft.dropdown.Option(key="large-v3", text="large-v3 (~3.1 GB, макс.)"),
            ],
            value=_cur_model,
            text_size=13,
            on_change=self._change_whisper_model,
        )

        self.btn_record = ft.ElevatedButton(
            icon=ft.icons.FIBER_MANUAL_RECORD_ROUNDED, 
            text="Запись",
            bgcolor=ft.colors.BLUE_700,
            color=ft.colors.WHITE,
            on_click=self.toggle_record,
            width=150
        )
        
        self.pulse_ring = ft.ProgressRing(width=24, height=24, stroke_width=2, color=ft.colors.RED_400, visible=False)
        self.status_text = ft.Text("Готов", size=12, color=ft.colors.ON_SURFACE_VARIANT)

        sidebar = ft.Container(
            width=280,
            padding=20,
            bgcolor=ft.colors.SURFACE,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Column([
                ft.Text("Устройства", weight=ft.FontWeight.BOLD),
                self.dd_input,
                self.dd_output,
                ft.TextButton("Обновить список", icon=ft.icons.REFRESH, on_click=self.refresh_devices),
                ft.Divider(height=20),
                ft.Text("Настройки", weight=ft.FontWeight.BOLD),
                self.dd_language,
                self.dd_whisper,
                ft.Divider(height=20),
                ft.Row([self.btn_record, self.pulse_ring], alignment=ft.MainAxisAlignment.START),
                self.status_text,
                ft.Container(expand=True),
                ft.ElevatedButton("Очистить историю", icon=ft.icons.DELETE_SWEEP, on_click=self.clear_history, color=ft.colors.RED_300),
            ])
        )

        # Main Content Area
        self.transcript_view = ft.ListView(expand=True, spacing=10, auto_scroll=True)
        self.summary_text = ft.Markdown(selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB)
        self.pr_summary = ft.ProgressBar(visible=False, color=ft.colors.BLUE_400)

        self.tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            expand=True,
            tabs=[
                ft.Tab(
                    text="Транскрипт",
                    icon=ft.icons.FORUM_ROUNDED,
                    content=ft.Container(
                        padding=20,
                        content=self.transcript_view
                    )
                ),
                ft.Tab(
                    text="Саммари",
                    icon=ft.icons.SUMMARIZE_ROUNDED,
                    content=ft.Container(
                        padding=20,
                        content=ft.Column([
                            ft.Row([
                                ft.ElevatedButton("Генерировать Саммари", icon=ft.icons.AUTO_AWESOME, on_click=self.generate_summary),
                                self.pr_summary
                            ]),
                            ft.Divider(),
                            ft.ListView([self.summary_text], expand=True)
                        ])
                    )
                ),
            ]
        )

        # Layout
        self.page.add(
            ft.Row([
                sidebar,
                ft.VerticalDivider(width=1),
                ft.Container(content=self.tabs, expand=True, bgcolor=ft.colors.SURFACE)
            ], expand=True)
        )
