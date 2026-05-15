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

        self.transcription_buffer = []

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

        self.version = get_version()
        self.page.title = f"AI Meetings v{self.version}"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.width = 1000
        self.page.window.height = 700
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
        self.speech_recognizer.language = lang

        if self.chatgpt_client:
            self.chatgpt_client.model = self.dd_llm.value

        try:
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
                    self.append_transcription(transcription, speaker)
            time.sleep(0.1)

    def append_transcription(self, text, speaker):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        is_local = speaker == "local"
        speaker_name = "Я" if is_local else "Собеседник"
        color = ft.colors.BLUE_400 if is_local else ft.colors.GREEN_400

        self.transcription_buffer.append({"text": text, "speaker": speaker_name})
        
        if self.chatgpt_client:
            self.chatgpt_client.add_message(f"[{speaker_name}]: {text}", role="user")

        msg = ft.Container(
            content=ft.Column([
                ft.Text(f"{speaker_name} • {ts}", color=color, size=12, weight=ft.FontWeight.BOLD),
                ft.Text(text, size=14)
            ], spacing=2),
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
        if self.chatgpt_client:
            self.chatgpt_client.clear_conversation()
        self.transcript_view.controls.clear()
        self.summary_text.value = ""
        self.status_text.value = "История очищена"
        self.page.update()

    def show_snack(self, text, color):
        self.page.snack_bar = ft.SnackBar(ft.Text(text), bgcolor=color)
        self.page.snack_bar.open = True
        self.page.update()

    def apply_api_settings(self, e=None):
        if not self.chatgpt_client: return
        self.chatgpt_client.base_url = self.tb_base_url.value.strip() or None
        if self.tb_api_key.value.strip():
            self.chatgpt_client.api_key = self.tb_api_key.value.strip()
        self.chatgpt_client.model = self.dd_llm.value
        self.show_snack("Настройки применены", ft.colors.GREEN_600)
        
        # Save to .env logic can go here

    def setup_ui(self):
        # Top App Bar
        self.page.appbar = ft.AppBar(
            title=ft.Text(f"AI Meetings v{self.version}", weight=ft.FontWeight.BOLD),
            center_title=False,
            bgcolor=ft.colors.SURFACE_VARIANT,
            actions=[
                ft.IconButton(ft.icons.SETTINGS, on_click=lambda e: setattr(self.settings_dlg, 'open', True) or self.page.update()),
                ft.Container(width=10)
            ]
        )

        # Settings Dialog
        self.tb_api_key = ft.TextField(label="API Key (OpenAI)", password=True, can_reveal_password=True)
        self.tb_base_url = ft.TextField(label="Base URL (пусто = OpenAI, или LM Studio: http://127.0.0.1:1234/v1)")
        self.dd_llm = ft.Dropdown(label="LLM Model", options=[
            ft.dropdown.Option("gpt-4o"), ft.dropdown.Option("gpt-4-turbo"), ft.dropdown.Option("gpt-3.5-turbo")
        ], value="gpt-4o")

        self.settings_dlg = ft.AlertDialog(
            title=ft.Text("Настройки API"),
            content=ft.Column([self.tb_api_key, self.tb_base_url, self.dd_llm], tight=True),
            actions=[ft.TextButton("Применить", on_click=lambda e: [self.apply_api_settings(), setattr(self.settings_dlg, 'open', False), self.page.update()])]
        )
        self.page.overlay.append(self.settings_dlg)

        # Sidebar (Devices & Controls)
        self.dd_input = ft.Dropdown(label="Микрофон", text_size=13)
        self.dd_output = ft.Dropdown(label="Системный звук (Динамики)", text_size=13)
        self.dd_language = ft.Dropdown(label="Язык", options=[
            ft.dropdown.Option("ru"), ft.dropdown.Option("en"), ft.dropdown.Option("auto")
        ], value="ru", text_size=13)

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
            content=ft.Column([
                ft.Text("Устройства", weight=ft.FontWeight.BOLD),
                self.dd_input,
                self.dd_output,
                ft.TextButton("Обновить список", icon=ft.icons.REFRESH, on_click=self.refresh_devices),
                ft.Divider(height=20),
                ft.Text("Настройки", weight=ft.FontWeight.BOLD),
                self.dd_language,
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
