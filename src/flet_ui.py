import flet as ft
import os
import datetime
import threading
import time

from utils.config import UI_SETTINGS, CHATGPT_SETTINGS, SPEECH_RECOGNITION, MDELTA_THEME

# Дизайн-токены MDelta (см. utils/config.py)
_C_PRIMARY = MDELTA_THEME['primary']
_C_BG = MDELTA_THEME['bg_layout']
_C_CARD = MDELTA_THEME['bg_container']
_C_BORDER = MDELTA_THEME['border']
_C_TEXT = MDELTA_THEME['text']
_C_TEXT2 = MDELTA_THEME['text_secondary']
_C_ERROR = MDELTA_THEME['error']
_C_SUCCESS = MDELTA_THEME['success']
_RADIUS = MDELTA_THEME['radius']


def _find_asset(filename: str):
    """Ищет файл ассета: в PyInstaller bundle (_MEIPASS) или в installer/assets."""
    import sys
    candidates = []
    if hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, filename))
    candidates.append(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'installer', 'assets', filename,
    ))
    return next((p for p in candidates if os.path.exists(p)), None)


def _apply_win32_icon(icon_path: str, window_title: str) -> None:
    """Override the Flutter window icon via Win32 WM_SETICON in a background thread.

    Flet's Flutter binary has its own icon baked in; page.window.icon asks the
    window_manager plugin to change it, but that can race with window creation.
    This fallback polls for the HWND and forces the HICON directly.
    """
    import sys
    if sys.platform != 'win32':
        return

    def _worker():
        try:
            import ctypes
            user32 = ctypes.windll.user32
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x10
            LR_DEFAULTSIZE = 0x40
            WM_SETICON = 0x80

            hicon = user32.LoadImageW(
                0, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
            )
            if not hicon:
                return
            for _ in range(20):
                time.sleep(0.3)
                hwnd = user32.FindWindowW(None, window_title)
                if hwnd:
                    user32.SendMessageW(hwnd, WM_SETICON, 0, hicon)  # ICON_SMALL
                    user32.SendMessageW(hwnd, WM_SETICON, 1, hicon)  # ICON_BIG
                    return
        except Exception as e:
            print(f"[icon] Win32 fallback: {e}")

    threading.Thread(target=_worker, daemon=True).start()


class FletAudioAssistantUI:
    # Отображается в дропдауне модели, когда native whisper.cpp сервер
    # не отдаёт список моделей (модель задана на самом сервере)
    _NATIVE_MODEL_LABEL = "(модель задаётся на сервере)"

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

        self.version = get_version()
        self.page.title = f"{UI_SETTINGS['window_title']} v{self.version}"
        icon_path = _find_asset('icon.ico')
        if icon_path:
            self.page.window.icon = icon_path
            _apply_win32_icon(icon_path, self.page.title)
        self.logo_path = _find_asset('logo.png')

        # Светлая тема в дизайн-системе MDelta (Ant Design v5)
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.bgcolor = _C_BG
        self.page.window.width = UI_SETTINGS['window_width']
        self.page.window.height = UI_SETTINGS['window_height']
        self.page.padding = 0
        self.page.fonts = {
            "Inter": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
        }
        self.page.theme = ft.Theme(font_family="Inter", color_scheme_seed=_C_PRIMARY)

        self.setup_ui()
        self.refresh_devices()

    # Максимум символов имени устройства в дропдауне — длинные имена
    # (Bluetooth-гарнитуры) вылезают за границы контрола
    _DEVICE_LABEL_MAX = 34

    @classmethod
    def _device_option(cls, idx, name):
        """Option с key=индекс и усечённым текстом (полное имя — вне контрола)."""
        label = f"{idx}: {name}"
        if len(label) > cls._DEVICE_LABEL_MAX:
            label = label[:cls._DEVICE_LABEL_MAX - 1] + "…"
        return ft.dropdown.Option(key=str(idx), text=label)

    # Специальное значение «устройство по умолчанию ОС» — следует за
    # выбором в настройках Windows, а не за конкретным устройством
    DEFAULT_DEVICE_KEY = "default"
    _DEFAULT_DEVICE_LABEL = "Устройство по умолчанию (ОС)"

    def refresh_devices(self, e=None):
        if not self.audio_capture: return
        input_devices = self.audio_capture.list_input_devices()
        output_devices = self.audio_capture.list_output_devices()

        default_opt = ft.dropdown.Option(
            key=self.DEFAULT_DEVICE_KEY, text=self._DEFAULT_DEVICE_LABEL)

        self.dd_input.options = [default_opt] + \
            [self._device_option(idx, name) for idx, name, _ in input_devices]
        self.dd_output.options = [ft.dropdown.Option(
            key=self.DEFAULT_DEVICE_KEY, text=self._DEFAULT_DEVICE_LABEL)] + \
            [self._device_option(idx, name) for idx, name, _ in output_devices]

        # Сохраняем выбор пользователя между обновлениями списка;
        # по умолчанию — «Устройство по умолчанию (ОС)»
        in_keys = {o.key for o in self.dd_input.options}
        out_keys = {o.key for o in self.dd_output.options}
        if self.dd_input.value not in in_keys:
            self.dd_input.value = self.DEFAULT_DEVICE_KEY
        if self.dd_output.value not in out_keys:
            self.dd_output.value = self.DEFAULT_DEVICE_KEY

        self.page.update()

    @classmethod
    def _parse_device_index(cls, value):
        """'default'/пусто → None (устройство по умолчанию ОС), иначе int-индекс."""
        if value in (None, '', cls.DEFAULT_DEVICE_KEY):
            return None
        return int(str(value).split(":")[0])

    def start_recording(self):
        if not self.audio_capture or not self.speech_recognizer:
            self.show_snack("Ошибка: компоненты не инициализированы", ft.colors.RED_400)
            return

        try:
            in_idx = self._parse_device_index(self.dd_input.value)
            out_idx = self._parse_device_index(self.dd_output.value)
        except Exception:
            self.show_snack("Ошибка выбора устройств", ft.colors.RED_400)
            return

        if self.chatgpt_client:
            self.chatgpt_client.model = self.dd_llm.value

        # Источник распознавания (модель/сервер) проверяется здесь, при старте
        # записи, а не при запуске приложения. Модель качается только сейчас.
        rec = self.speech_recognizer
        if getattr(rec, 'is_ready', True) is False:
            self.btn_record.disabled = True
            self.status_text.value = "Подготовка распознавания речи..."
            self.page.update()

            def _prepare():
                try:
                    rec.ensure_ready(status_cb=self._set_status)
                except Exception as ex:
                    self.btn_record.disabled = False
                    self.status_text.value = "Распознавание недоступно"
                    self.show_snack(f"{ex}", _C_ERROR)
                    self.page.update()
                    return
                self.btn_record.disabled = False
                self._begin_recording(in_idx, out_idx)

            threading.Thread(target=_prepare, daemon=True).start()
            return

        self._begin_recording(in_idx, out_idx)

    def _set_status(self, msg: str):
        self.status_text.value = msg
        self.page.update()

    def _begin_recording(self, in_idx: int, out_idx: int):
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
            self.btn_record.bgcolor = _C_ERROR
            self.status_text.value = "Идёт запись..."
            self.pulse_ring.visible = True
            self.page.update()

            # Watchdog: если через несколько секунд с микрофона не пришло
            # ни байта — устройство молчит (выключена гарнитура и т.п.)
            started_at = getattr(self.audio_capture, 'session_start', None)
            watchdog = threading.Timer(5.0, self._check_audio_signal, args=(started_at,))
            watchdog.daemon = True
            watchdog.start()

        except Exception as e:
            self.show_snack(f"Ошибка записи: {e}", ft.colors.RED_400)

    def _check_audio_signal(self, started_at):
        """Проверка (по таймеру) что с микрофона реально идёт звук."""
        if not self.is_recording or not self.audio_capture:
            return
        if getattr(self.audio_capture, 'session_start', None) is not started_at:
            return  # уже другая сессия
        pcm = getattr(self.audio_capture, 'session_pcm', b'')
        if isinstance(pcm, (bytes, bytearray)) and len(pcm) == 0:
            self.status_text.value = "⚠ Нет сигнала с микрофона"
            self.show_snack(
                "С микрофона не поступает звук. Проверьте, что устройство включено "
                "(Bluetooth-гарнитура — активна), и обновите список устройств.",
                ft.colors.ORANGE_400,
            )
            self.page.update()

    def stop_recording(self):
        if self.audio_capture:
            self.audio_capture.stop_recording()
        
        self.is_recording = False
        self.is_processing = False

        self.btn_record.icon = ft.icons.FIBER_MANUAL_RECORD_ROUNDED
        self.btn_record.text = "Запись"
        self.btn_record.bgcolor = _C_PRIMARY
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
            # Любая ошибка одного сегмента не должна убивать поток обработки —
            # иначе запись продолжается, а транскрипция молча умирает
            try:
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
            except Exception as e:
                print(f"[UI] Ошибка обработки сегмента: {e}")
            time.sleep(0.1)

    def append_transcription(self, text, speaker, polished=False, start_time=None):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        is_local = speaker == "local"
        speaker_name = "Я" if is_local else "Собеседник"
        color = ft.colors.BLUE_400 if is_local else ft.colors.GREEN_400

        self.transcription_buffer.append({"text": text, "speaker": speaker_name})

        msg_id = None
        if self.chatgpt_client:
            msg_id = self.chatgpt_client.add_message(f"[{speaker_name}]: {text}", role="user")

        # Смещение от начала сессии — нужно для диаризации обеих дорожек
        # (mic → Участник N, системный звук → Собеседник N)
        start_offset = None
        if start_time is not None and self.audio_capture and self.audio_capture.session_start:
            start_offset = max(0.0, (start_time - self.audio_capture.session_start).total_seconds())

        speaker_ctrl = ft.Text(speaker_name, color=color, size=12, weight=ft.FontWeight.BOLD)

        # Create entry early so button callbacks can capture it via default-arg binding
        entry = {
            "start_offset": start_offset,
            "speaker_raw": speaker,
            "speaker_ctrl": speaker_ctrl,
            "msg_id": msg_id,
            "ts": ts,
        }

        edit_btn = ft.IconButton(
            ft.icons.EDIT_OUTLINED, icon_size=14, icon_color=ft.colors.GREY_600,
            tooltip="Редактировать",
            on_click=lambda e, ent=entry: self._start_edit(ent),
        )
        llm_btn = ft.IconButton(
            ft.icons.AUTO_AWESOME, icon_size=14, icon_color=ft.colors.GREY_600,
            tooltip="Улучшить через LLM",
            on_click=lambda e, ent=entry: self._llm_polish_entry(ent),
        )

        header_row = ft.Row([
            speaker_ctrl,
            ft.Text(f" • {ts}", color=ft.colors.GREY_500, size=12),
            ft.Row([edit_btn, llm_btn], spacing=0),
            *(
                [ft.Icon(ft.icons.AUTO_AWESOME, size=12, color=ft.colors.AMBER_400,
                         tooltip="Улучшено LLM")]
                if polished else []
            ),
        ], spacing=4)

        text_ctrl = ft.Text(text, size=14)
        content_col = ft.Column([header_row, text_ctrl], spacing=2)
        entry["text_ctrl"] = text_ctrl
        entry["col"] = content_col

        self._transcript_entries.append(entry)

        msg = ft.Container(
            content=content_col,
            bgcolor='#E6F4FF' if is_local else _C_CARD,
            border=ft.border.all(1, '#BAE0FF' if is_local else _C_BORDER),
            padding=12,
            border_radius=_RADIUS,
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

    _MIN_DIAR_PCM = 2 * 16000 * 2  # минимум 2 секунды int16

    def _try_diarize(self):
        """Диаризация обеих дорожек по окончании записи.

        mic ("Я")            → «Участник 1/2/…» если говоривших несколько
        системный звук       → «Собеседник 1/2/…» если собеседников несколько
        """
        try:
            from src import diarization as diar
        except ImportError:
            return
        if not diar.is_available():
            return
        if not self.audio_capture:
            return

        tasks = []
        pcm_local = self.audio_capture.session_pcm
        local_entries = [e for e in self._transcript_entries if e["speaker_raw"] == "local"]
        if len(pcm_local) >= self._MIN_DIAR_PCM and local_entries:
            tasks.append((pcm_local, local_entries, "Участник", "Я",
                          self._DIAR_COLORS, ft.colors.BLUE_400))

        pcm_sys = getattr(self.audio_capture, 'session_sys_pcm', b'')
        remote_entries = [e for e in self._transcript_entries if e["speaker_raw"] == "remote"]
        if len(pcm_sys) >= self._MIN_DIAR_PCM and remote_entries:
            tasks.append((pcm_sys, remote_entries, "Собеседник", "Собеседник",
                          self._DIAR_COLORS_REMOTE, ft.colors.GREEN_400))

        if not tasks:
            return

        def _run():
            try:
                def status_cb(msg):
                    self.status_text.value = msg
                    self.page.update()
                for pcm, entries, prefix, single, palette, single_color in tasks:
                    status_cb(f"Диаризация ({prefix.lower()})...")
                    try:
                        segments = diar.diarize(pcm, status_cb=status_cb)
                        self._apply_diarization(segments, entries, prefix=prefix,
                                                single_label=single, palette=palette,
                                                single_color=single_color)
                    except Exception as e:
                        print(f"[Diarization] Ошибка ({prefix}): {e}")
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

    # Палитра для собеседников (системный звук) — отличается от палитры
    # участников с микрофона, чтобы стороны разговора читались сразу
    _DIAR_COLORS_REMOTE = [
        ft.colors.GREEN_400,
        ft.colors.CYAN_600,
        ft.colors.LIME_700,
        ft.colors.AMBER_600,
    ]

    def _apply_diarization(self, segments, entries, prefix="Участник",
                           single_label="Я", palette=None, single_color=None):
        """Перемаркирует entries по результатам диаризации.

        prefix       — метка спикера с номером («Участник 2», «Собеседник 1»)
        single_label — метка если обнаружен только один говорящий
        """
        palette = palette or self._DIAR_COLORS
        single_color = single_color or ft.colors.BLUE_400
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
                speaker_map[sid] = (f"{prefix} {n}", palette[(n - 1) % len(palette)])
            label, color = speaker_map[sid]
            entry["speaker_ctrl"].value = label
            entry["speaker_ctrl"].color = color

        if len(speaker_map) <= 1:
            for entry in entries:
                entry["speaker_ctrl"].value = single_label
                entry["speaker_ctrl"].color = single_color

        self.page.update()

    # ── Редактирование транскрипта ────────────────────────────────────────────

    def _start_edit(self, entry):
        if entry.get("editing"):
            return
        old_text = entry["text_ctrl"].value
        entry["old_text"] = old_text
        entry["editing"] = True

        tf = ft.TextField(
            value=old_text, multiline=True, min_lines=1, max_lines=6,
            dense=True, expand=True, border_color=ft.colors.BLUE_400, text_size=14,
        )
        entry["edit_field"] = tf

        save_btn = ft.IconButton(
            ft.icons.CHECK_ROUNDED, icon_size=18, icon_color=ft.colors.GREEN_400,
            tooltip="Сохранить", on_click=lambda e: self._finish_edit(entry),
        )
        cancel_btn = ft.IconButton(
            ft.icons.CLOSE_ROUNDED, icon_size=18, icon_color=ft.colors.RED_400,
            tooltip="Отмена", on_click=lambda e: self._cancel_edit(entry),
        )
        entry["col"].controls[1] = ft.Row(
            [tf, save_btn, cancel_btn], vertical_alignment=ft.CrossAxisAlignment.START
        )
        self.page.update()

    def _finish_edit(self, entry):
        new_text = (entry.get("edit_field") or ft.TextField()).value.strip()
        if not new_text:
            self._cancel_edit(entry)
            return

        old_text = entry.get("old_text", "")
        entry["text_ctrl"].value = new_text
        entry["col"].controls[1] = entry["text_ctrl"]
        entry["editing"] = False

        for item in self.transcription_buffer:
            if item["text"] == old_text:
                item["text"] = new_text
                break

        self._sync_history(entry, new_text)
        self.page.update()

    def _cancel_edit(self, entry):
        entry["col"].controls[1] = entry["text_ctrl"]
        entry["editing"] = False
        self.page.update()

    def _sync_history(self, entry, new_text):
        if not self.chatgpt_client or entry.get("msg_id") is None:
            return
        new_content = f"[{entry['speaker_ctrl'].value}]: {new_text}"
        for msg in self.chatgpt_client.conversation_history:
            if msg.get("_id") == entry["msg_id"]:
                msg["content"] = new_content
                return

    def _llm_polish_entry(self, entry):
        if not self.chatgpt_client or entry.get("editing"):
            return
        original = entry["text_ctrl"].value

        def _run():
            try:
                improved = self.chatgpt_client.polish_transcription(original)
                if improved and improved.strip() != original.strip():
                    entry["text_ctrl"].value = improved
                    for item in self.transcription_buffer:
                        if item["text"] == original:
                            item["text"] = improved
                            break
                    self._sync_history(entry, improved)
                    self.page.update()
            except Exception as e:
                print(f"[LLM] Ошибка улучшения сегмента: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _apply_global_correction(self):
        instruction = self.tb_correction.value.strip()
        if not instruction:
            self.show_snack("Введите инструкцию", ft.colors.ORANGE_400)
            return
        if not self.chatgpt_client:
            self.show_snack("LLM не подключён", ft.colors.ORANGE_400)
            return

        entries = [e for e in self._transcript_entries if not e.get("editing")]
        if not entries:
            self.show_snack("Нет записей для правки", ft.colors.ORANGE_400)
            return

        self.status_text.value = "Применяю правку..."
        self.page.update()

        def _run():
            try:
                for entry in entries:
                    original = entry["text_ctrl"].value
                    improved = self.chatgpt_client.correct_text(original, instruction)
                    if improved and improved.strip() != original.strip():
                        entry["text_ctrl"].value = improved
                        for item in self.transcription_buffer:
                            if item["text"] == original:
                                item["text"] = improved
                                break
                        self._sync_history(entry, improved)
                self.status_text.value = "Правка применена"
                self.tb_correction.value = ""
            except Exception as e:
                self.show_snack(f"Ошибка: {e}", ft.colors.RED_400)
                self.status_text.value = "Готов"
            finally:
                self.page.update()

        threading.Thread(target=_run, daemon=True).start()

    def show_snack(self, text, color):
        self.page.snack_bar = ft.SnackBar(ft.Text(text), bgcolor=color)
        self.page.snack_bar.open = True
        self.page.update()

    # ── Копирование транскрипта и саммари ─────────────────────────────────────

    def _transcript_as_text(self) -> str:
        """Транскрипт в виде текста: [HH:MM:SS] Спикер: реплика.

        Использует актуальные метки спикеров (после диаризации —
        «Участник N» / «Собеседник N») и отредактированный текст.
        """
        lines = []
        for entry in self._transcript_entries:
            speaker = entry["speaker_ctrl"].value
            text = entry["text_ctrl"].value if entry.get("text_ctrl") else ""
            ts = entry.get("ts", "")
            prefix = f"[{ts}] " if ts else ""
            lines.append(f"{prefix}{speaker}: {text}")
        return "\n".join(lines)

    def _copy_transcript(self, e=None):
        text = self._transcript_as_text()
        if not text.strip():
            self.show_snack("Транскрипт пуст", ft.colors.ORANGE_400)
            return
        self.page.set_clipboard(text)
        self.show_snack("Транскрипт скопирован в буфер обмена", _C_SUCCESS)

    def _copy_summary(self, e=None):
        text = (self.summary_text.value or "").strip()
        if not text:
            self.show_snack("Саммари ещё не сгенерировано", ft.colors.ORANGE_400)
            return
        self.page.set_clipboard(text)
        self.show_snack("Саммари скопировано в буфер обмена", _C_SUCCESS)

    def apply_api_settings(self, e=None):
        if not self.chatgpt_client: return

        # ── LLM: Inference ИЛИ MDelta API ─────────────────────────────────────
        provider = self.rg_llm.value or 'inference'
        api_key = self.tb_api_key.value.strip()
        base_url = self.tb_base_url.value.strip()
        model = self.dd_llm.value

        client = self.chatgpt_client
        client.provider = provider
        client.base_url = base_url or None
        if api_key:
            client.api_key = api_key
        client.model = model
        client.mdelta_base_url = self.tb_mdelta_url.value.strip()
        client.mdelta_username = self.tb_mdelta_user.value.strip()
        client.mdelta_password = self.tb_mdelta_pass.value.strip()
        client._reinit_client()

        self.postprocess_enabled = self.sw_postprocess.value

        # ── STT: локально ИЛИ удалённый Whisper-сервер ────────────────────────
        stt_mode = self.rg_stt.value or 'local'
        stt_url = self.tb_stt_url.value.strip()
        stt_key = self.tb_stt_key.value.strip()
        stt_model = self.dd_stt_model.value or 'whisper-1'
        if stt_model == self._NATIVE_MODEL_LABEL:
            # псевдо-значение для native whisper.cpp — сервер игнорирует model
            stt_model = 'whisper-1'
        self._apply_stt_source(stt_mode, stt_url, stt_key, stt_model)

        if self.env_path:
            self._save_env(api_key, base_url, model, extra={
                'LLM_PROVIDER': provider,
                'MDELTA_API_URL': client.mdelta_base_url,
                'MDELTA_USERNAME': client.mdelta_username,
                'MDELTA_PASSWORD': client.mdelta_password,
                'WHISPER_MODE': stt_mode,
                'WHISPER_REMOTE_URL': stt_url,
                'WHISPER_REMOTE_KEY': stt_key,
                'WHISPER_REMOTE_MODEL': stt_model,
            })

        self.show_snack("Настройки применены", _C_SUCCESS)

    def _apply_stt_source(self, mode: str, url: str, key: str, model: str):
        """Асинхронно переключает источник распознавания речи (backend может грузиться долго)."""
        if not self.speech_recognizer:
            return
        rec = self.speech_recognizer
        current_mode = getattr(rec, 'mode', 'local')
        if mode == current_mode and (
            mode == 'local' or (
                url == getattr(rec, 'remote_base_url', '')
                and key == getattr(rec, 'remote_api_key', '')
                and model == getattr(rec, 'remote_model', '')
            )
        ):
            self._update_stt_ui_state()
            return

        self.btn_record.disabled = True
        self.status_text.value = "Переключение источника распознавания..."
        self.page.update()

        def _do():
            try:
                rec.configure_source(mode, url, key, model)
                if getattr(rec, 'is_ready', False):
                    self.status_text.value = f"STT: {rec.active_backend_name}"
                else:
                    # Отложенная инициализация: источник проверится при записи
                    self.status_text.value = "Источник сохранён — проверка при записи"
            except Exception as ex:
                self.status_text.value = "Ошибка переключения STT"
                self.show_snack(f"Ошибка STT: {ex}", _C_ERROR)
            finally:
                self.btn_record.disabled = False
                self._update_stt_ui_state()
                self.page.update()

        threading.Thread(target=_do, daemon=True).start()

    def _update_stt_ui_state(self):
        """Сайдбар отражает активный источник STT.

        local  → дропдаун локальной модели;
        remote → вместо него бейдж с адресом сервера и моделью.
        """
        rec = self.speech_recognizer
        remote = getattr(rec, 'mode', 'local') == 'remote' if rec else False
        self.dd_whisper.visible = not remote
        self.dd_whisper.disabled = remote
        if hasattr(self, 'remote_stt_badge'):
            self.remote_stt_badge.visible = remote
            if remote:
                url = getattr(rec, 'remote_base_url', '') or '—'
                backend = getattr(rec, '_backend', None)
                if backend is not None and getattr(backend, 'api_style', '') == 'whispercpp':
                    model = 'модель на сервере'
                else:
                    model = getattr(rec, 'remote_model', '') or 'whisper-1'
                self.txt_remote_stt.value = f"{url}\n{model}"

    def _save_env(self, api_key: str, base_url: str, model: str,
                  whisper_model: str = None, extra: dict = None):
        """Сохраняет настройки в .env файл. extra — дополнительные пары KEY=value."""
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
            for key, value in (extra or {}).items():
                if value:
                    lines = set_var(lines, key, value)

            os.makedirs(os.path.dirname(self.env_path), exist_ok=True)
            with open(self.env_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        except Exception as ex:
            print(f"[Settings] Не удалось сохранить .env: {ex}")

    def _open_settings(self, e=None):
        if self.chatgpt_client:
            client = self.chatgpt_client
            key = client.api_key or ''
            if key == 'local':
                key = ''
            self.tb_api_key.value = key
            self.tb_base_url.value = client.base_url or ''
            # Текущая модель может отсутствовать в списке (задана через .env) —
            # добавляем её в options, иначе Dropdown отобразится пустым
            if client.model and client.model not in [o.key for o in self.dd_llm.options]:
                self.dd_llm.options.append(ft.dropdown.Option(client.model))
            self.dd_llm.value = client.model
            self.rg_llm.value = getattr(client, 'provider', 'inference')
            self.tb_mdelta_url.value = getattr(client, 'mdelta_base_url', '') or ''
            self.tb_mdelta_user.value = getattr(client, 'mdelta_username', '') or ''
            self.tb_mdelta_pass.value = getattr(client, 'mdelta_password', '') or ''
        if self.speech_recognizer:
            rec = self.speech_recognizer
            self.rg_stt.value = getattr(rec, 'mode', 'local')
            self.tb_stt_url.value = getattr(rec, 'remote_base_url', '') or ''
            self.tb_stt_key.value = getattr(rec, 'remote_api_key', '') or ''
            remote_model = getattr(rec, 'remote_model', 'whisper-1') or 'whisper-1'
            self._set_stt_model_options([remote_model])
            self.dd_stt_model.value = remote_model
        self.sw_postprocess.value = self.postprocess_enabled
        self._toggle_provider_fields()
        self._toggle_stt_fields()
        # Высота диалога под окно: скролл появляется только когда реально
        # не хватает места, а не на любом разрешении
        page_h = getattr(self.page, 'height', None)
        if not isinstance(page_h, (int, float)) or page_h <= 0:
            page_h = 720
        self._settings_col.height = max(360, min(680, int(page_h) - 200))
        self.settings_dlg.open = True
        self.page.update()

    def _set_stt_model_options(self, models: list):
        current = self.dd_stt_model.value
        opts = list(dict.fromkeys((models or []) + ([current] if current else [])))
        self.dd_stt_model.options = [ft.dropdown.Option(m) for m in opts]

    def _toggle_provider_fields(self, e=None):
        is_mdelta = (self.rg_llm.value == 'mdelta')
        self.inference_fields.visible = not is_mdelta
        self.mdelta_fields.visible = is_mdelta
        if e is not None:
            self.page.update()

    def _toggle_stt_fields(self, e=None):
        self.remote_stt_fields.visible = (self.rg_stt.value == 'remote')
        if e is not None:
            self.page.update()

    def _fetch_stt_models(self, e=None):
        """Загружает список моделей с удалённого Whisper-сервера (GET /models)."""
        base_url = self.tb_stt_url.value.strip()
        api_key = self.tb_stt_key.value.strip()
        if not base_url:
            self.show_snack("Укажите URL Whisper-сервера", _C_ERROR)
            return

        def _do():
            try:
                from src.speech_recognition import fetch_remote_whisper_models
                models = fetch_remote_whisper_models(base_url, api_key)
                if models:
                    self._set_stt_model_options(models)
                    if self.dd_stt_model.value not in models:
                        self.dd_stt_model.value = models[0]
                    self.page.update()
                    self.show_snack(f"Загружено {len(models)} моделей", _C_SUCCESS)
                else:
                    # Сервер жив, но /models не отдаёт — native whisper.cpp:
                    # модель задаётся на самом сервере
                    self._set_stt_model_options([self._NATIVE_MODEL_LABEL])
                    self.dd_stt_model.value = self._NATIVE_MODEL_LABEL
                    self.page.update()
                    self.show_snack(
                        "Сервер доступен (native whisper.cpp) — модель задаётся на сервере",
                        _C_SUCCESS,
                    )
            except Exception as ex:
                self.show_snack(f"Ошибка загрузки моделей: {ex}", _C_ERROR)

        threading.Thread(target=_do, daemon=True).start()

    def _test_mdelta_connection(self, e=None):
        """Проверяет подключение к MDelta API (логин по JWT)."""
        if not self.chatgpt_client:
            return
        url = self.tb_mdelta_url.value.strip()
        user = self.tb_mdelta_user.value.strip()
        pwd = self.tb_mdelta_pass.value.strip()
        if not url or not user:
            self.show_snack("Укажите URL и логин MDelta", _C_ERROR)
            return

        def _do():
            client = self.chatgpt_client
            prev = (client.mdelta_base_url, client.mdelta_username, client.mdelta_password)
            try:
                client.mdelta_base_url, client.mdelta_username, client.mdelta_password = url, user, pwd
                client.test_mdelta_connection()
                self.show_snack("Подключение к MDelta API успешно", _C_SUCCESS)
            except Exception as ex:
                client.mdelta_base_url, client.mdelta_username, client.mdelta_password = prev
                self.show_snack(f"Ошибка подключения к MDelta: {ex}", _C_ERROR)

        threading.Thread(target=_do, daemon=True).start()

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
        # ── Top App Bar: логотип-дельта + MDelta Meetings ─────────────────────
        logo_ctrl = (
            ft.Image(src=self.logo_path, width=28, height=28)
            if self.logo_path
            else ft.Icon(ft.icons.CHANGE_HISTORY_ROUNDED, color=_C_PRIMARY, size=28)
        )
        self.page.appbar = ft.AppBar(
            leading=ft.Container(content=logo_ctrl, padding=ft.padding.only(left=16)),
            leading_width=48,
            title=ft.Row([
                ft.Text("MDelta", size=18, weight=ft.FontWeight.BOLD, color=_C_TEXT),
                ft.Text("Meetings", size=18, color=_C_TEXT),
                ft.Container(
                    content=ft.Text(f"v{self.version}", size=11, color=_C_TEXT2),
                    bgcolor=_C_BG,
                    border_radius=4,
                    padding=ft.padding.symmetric(horizontal=6, vertical=2),
                    margin=ft.margin.only(left=4),
                ),
            ], spacing=5),
            center_title=False,
            bgcolor=_C_CARD,
            elevation=0,
            actions=[
                ft.IconButton(ft.icons.SETTINGS_OUTLINED, icon_color=_C_TEXT2,
                              tooltip="Настройки", on_click=self._open_settings),
                ft.Container(width=10)
            ]
        )

        # ── Диалог настроек ───────────────────────────────────────────────────
        def section_title(text):
            return ft.Text(text, size=13, weight=ft.FontWeight.BOLD, color=_C_TEXT)

        # — Секция: распознавание речи (Whisper) —
        self.rg_stt = ft.RadioGroup(
            value=SPEECH_RECOGNITION.get('mode', 'local'),
            on_change=self._toggle_stt_fields,
            content=ft.Column([
                ft.Radio(value="local", label="Локальная модель (WhisperNet / faster-whisper)"),
                ft.Radio(value="remote", label="Удалённый сервер (LM Studio / OpenAI-совместимый)"),
            ], spacing=0, tight=True),
        )
        self.tb_stt_url = ft.TextField(
            label="URL Whisper-сервера",
            hint_text="http://host:1234/v1 (LM Studio) · host:8082 (whisper.cpp)",
            helper_text="Тип API определяется автоматически: OpenAI-совместимый или native whisper.cpp",
            dense=True,
        )
        self.tb_stt_key = ft.TextField(label="API Key (если требуется)", password=True,
                                       can_reveal_password=True, dense=True)
        self.dd_stt_model = ft.Dropdown(
            label="Модель на сервере",
            options=[ft.dropdown.Option(SPEECH_RECOGNITION.get('remote_model', 'whisper-1'))],
            value=SPEECH_RECOGNITION.get('remote_model', 'whisper-1'),
            expand=True, dense=True,
        )
        self.remote_stt_fields = ft.Column([
            self.tb_stt_url,
            self.tb_stt_key,
            ft.Row([
                self.dd_stt_model,
                ft.IconButton(ft.icons.SYNC, tooltip="Загрузить список моделей с сервера",
                              on_click=self._fetch_stt_models),
            ], vertical_alignment=ft.CrossAxisAlignment.END),
        ], tight=True, spacing=8, visible=SPEECH_RECOGNITION.get('mode') == 'remote')

        # — Секция: LLM-провайдер (Inference ИЛИ MDelta API) —
        self.rg_llm = ft.RadioGroup(
            value=CHATGPT_SETTINGS.get('provider', 'inference'),
            on_change=self._toggle_provider_fields,
            content=ft.Column([
                ft.Radio(value="inference", label="Inference (OpenAI / LM Studio / Ollama)"),
                ft.Radio(value="mdelta", label="MDelta API"),
            ], spacing=0, tight=True),
        )

        self.tb_api_key = ft.TextField(label="API Key (OpenAI)", password=True,
                                       can_reveal_password=True, dense=True)
        self.tb_base_url = ft.TextField(
            label="Base URL",
            hint_text="пусто = OpenAI; LM Studio: http://127.0.0.1:1234/v1",
            dense=True,
        )
        self.dd_llm = ft.Dropdown(
            label="LLM Model",
            options=[
                ft.dropdown.Option("gpt-4o"),
                ft.dropdown.Option("gpt-4-turbo"),
                ft.dropdown.Option("gpt-3.5-turbo"),
            ],
            value=CHATGPT_SETTINGS.get('default_model', 'gpt-4o'),
            expand=True, dense=True,
        )
        self.inference_fields = ft.Column([
            self.tb_api_key,
            self.tb_base_url,
            ft.Row([
                self.dd_llm,
                ft.IconButton(ft.icons.SYNC, tooltip="Загрузить список моделей с сервера",
                              on_click=self._fetch_llm_models),
            ], vertical_alignment=ft.CrossAxisAlignment.END),
        ], tight=True, spacing=8,
            visible=CHATGPT_SETTINGS.get('provider', 'inference') != 'mdelta')

        self.tb_mdelta_url = ft.TextField(
            label="URL MDelta API",
            hint_text="https://mdrag.example.com",
            dense=True,
        )
        self.tb_mdelta_user = ft.TextField(label="Логин", dense=True)
        self.tb_mdelta_pass = ft.TextField(label="Пароль", password=True,
                                           can_reveal_password=True, dense=True)
        self.mdelta_fields = ft.Column([
            self.tb_mdelta_url,
            self.tb_mdelta_user,
            self.tb_mdelta_pass,
            ft.TextButton("Проверить подключение", icon=ft.icons.WIFI_TETHERING,
                          on_click=self._test_mdelta_connection),
        ], tight=True, spacing=8,
            visible=CHATGPT_SETTINGS.get('provider', 'inference') == 'mdelta')

        self.sw_postprocess = ft.Switch(
            label="LLM-улучшение качества",
            value=False,
            active_color=_C_PRIMARY,
            tooltip="Улучшать каждый фрагмент транскрипта через LLM: исправляет ошибки распознавания, пунктуацию, делает текст связным. Добавляет задержку на каждый фрагмент.",
        )

        self._settings_col = ft.Column([
            section_title("Распознавание речи (Whisper)"),
            self.rg_stt,
            self.remote_stt_fields,
            ft.Divider(height=16),
            section_title("Обработка и саммаризация (LLM)"),
            self.rg_llm,
            self.inference_fields,
            self.mdelta_fields,
            ft.Divider(height=16),
            self.sw_postprocess,
        ], tight=True, spacing=8, scroll=ft.ScrollMode.AUTO)

        self.settings_dlg = ft.AlertDialog(
            title=ft.Text("Настройки"),
            content=ft.Container(
                width=460,
                content=self._settings_col,
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: [setattr(self.settings_dlg, 'open', False), self.page.update()]),
                ft.FilledButton("Применить", on_click=lambda e: [self.apply_api_settings(), setattr(self.settings_dlg, 'open', False), self.page.update()]),
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
            label="Модель Whisper (локально)",
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

        # Бейдж активного удалённого Whisper-сервера (виден в remote-режиме
        # вместо дропдауна локальной модели)
        self.txt_remote_stt = ft.Text("", size=12, color=_C_TEXT, max_lines=3)
        self.remote_stt_badge = ft.Container(
            visible=False,
            bgcolor='#E6F4FF',
            border=ft.border.all(1, '#BAE0FF'),
            border_radius=_RADIUS,
            padding=10,
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.icons.CLOUD_OUTLINED, size=14, color=_C_PRIMARY),
                    ft.Text("Удалённый Whisper", size=12,
                            weight=ft.FontWeight.BOLD, color=_C_PRIMARY),
                ], spacing=6),
                self.txt_remote_stt,
            ], spacing=4, tight=True),
        )

        self.btn_record = ft.ElevatedButton(
            icon=ft.icons.FIBER_MANUAL_RECORD_ROUNDED,
            text="Запись",
            bgcolor=_C_PRIMARY,
            color=ft.colors.WHITE,
            elevation=0,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=_RADIUS)),
            on_click=self.toggle_record,
            width=160,
            height=40,
        )

        self.pulse_ring = ft.ProgressRing(width=24, height=24, stroke_width=2, color=_C_ERROR, visible=False)
        self.status_text = ft.Text("Готов", size=12, color=_C_TEXT2)

        self._update_stt_ui_state()

        sidebar = ft.Container(
            width=280,
            padding=20,
            bgcolor=_C_CARD,
            border=ft.border.only(right=ft.BorderSide(1, _C_BORDER)),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Column([
                ft.Text("Устройства", size=13, weight=ft.FontWeight.BOLD, color=_C_TEXT),
                self.dd_input,
                self.dd_output,
                ft.TextButton("Обновить список", icon=ft.icons.REFRESH, on_click=self.refresh_devices),
                ft.Divider(height=20, color=_C_BORDER),
                ft.Text("Распознавание", size=13, weight=ft.FontWeight.BOLD, color=_C_TEXT),
                self.dd_language,
                self.dd_whisper,
                self.remote_stt_badge,
                ft.Divider(height=20, color=_C_BORDER),
                ft.Row([self.btn_record, self.pulse_ring], alignment=ft.MainAxisAlignment.START),
                self.status_text,
                ft.Container(expand=True),
                ft.OutlinedButton(
                    "Очистить историю", icon=ft.icons.DELETE_SWEEP,
                    on_click=self.clear_history,
                    style=ft.ButtonStyle(
                        color=_C_ERROR,
                        shape=ft.RoundedRectangleBorder(radius=_RADIUS),
                        side=ft.BorderSide(1, _C_ERROR),
                    ),
                ),
            ])
        )

        # Main Content Area
        self.transcript_view = ft.ListView(expand=True, spacing=10, auto_scroll=True)
        self.tb_correction = ft.TextField(
            hint_text="Инструкция для LLM: замените 'GPT' на 'ChatGPT' во всём транскрипте...",
            expand=True,
            dense=True,
            text_size=13,
        )
        self.summary_text = ft.Markdown(selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB)
        self.pr_summary = ft.ProgressBar(visible=False, color=_C_PRIMARY)

        self.tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            expand=True,
            label_color=_C_PRIMARY,
            unselected_label_color=_C_TEXT2,
            indicator_color=_C_PRIMARY,
            divider_color=_C_BORDER,
            tabs=[
                ft.Tab(
                    text="Транскрипт",
                    icon=ft.icons.FORUM_ROUNDED,
                    content=ft.Container(
                        padding=ft.padding.only(left=20, right=20, top=20, bottom=8),
                        content=ft.Column([
                            self.transcript_view,
                            ft.Divider(height=8),
                            ft.Row([
                                self.tb_correction,
                                ft.IconButton(
                                    ft.icons.AUTO_FIX_HIGH,
                                    tooltip="Применить правку через LLM ко всему транскрипту",
                                    on_click=lambda e: self._apply_global_correction(),
                                ),
                                ft.IconButton(
                                    ft.icons.COPY_ROUNDED,
                                    icon_color=_C_PRIMARY,
                                    tooltip="Копировать весь транскрипт",
                                    on_click=self._copy_transcript,
                                ),
                            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ])
                    )
                ),
                ft.Tab(
                    text="Саммари",
                    icon=ft.icons.SUMMARIZE_ROUNDED,
                    content=ft.Container(
                        padding=20,
                        content=ft.Column([
                            ft.Row([
                                ft.FilledButton(
                                    "Генерировать Саммари", icon=ft.icons.AUTO_AWESOME,
                                    on_click=self.generate_summary,
                                    style=ft.ButtonStyle(
                                        bgcolor=_C_PRIMARY,
                                        shape=ft.RoundedRectangleBorder(radius=_RADIUS),
                                    ),
                                ),
                                ft.OutlinedButton(
                                    "Копировать", icon=ft.icons.COPY_ROUNDED,
                                    on_click=self._copy_summary,
                                    style=ft.ButtonStyle(
                                        color=_C_PRIMARY,
                                        shape=ft.RoundedRectangleBorder(radius=_RADIUS),
                                        side=ft.BorderSide(1, _C_PRIMARY),
                                    ),
                                ),
                                self.pr_summary
                            ]),
                            ft.Divider(color=_C_BORDER),
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
                ft.Container(content=self.tabs, expand=True, bgcolor=_C_BG)
            ], spacing=0, expand=True)
        )
