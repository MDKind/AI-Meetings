import os
import struct
import subprocess
import sys
import tempfile
import threading
import traceback
import wave
import uuid
import numpy as np
from utils.config import SPEECH_RECOGNITION


# ---------------------------------------------------------------------------
# GGML model download helper
# ---------------------------------------------------------------------------

GGML_MODEL_URLS = {
    'tiny':       'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin',
    'base':       'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin',
    'small':      'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin',
    'medium':     'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin',
    'large':      'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin',
    'large-v3':   'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin',
    'large-v3-turbo': 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin',
    'turbo':      'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin',
}

def _ggml_model_path(model_name: str) -> str:
    """Возвращает путь к GGML модели, скачивая если нужно."""
    models_dir = os.path.join(
        os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
        'AI Meetings', 'models'
    )
    os.makedirs(models_dir, exist_ok=True)

    filename = f'ggml-{model_name}.bin'
    path = os.path.join(models_dir, filename)

    if os.path.exists(path):
        return path

    url = GGML_MODEL_URLS.get(model_name)
    if not url:
        raise ValueError(f"Неизвестная GGML модель: {model_name}. Доступны: {list(GGML_MODEL_URLS)}")

    print(f"[WhisperNet] Скачивание модели {model_name} из {url} ...")
    import urllib.request

    def _progress(count, block_size, total_size):
        if total_size > 0:
            pct = count * block_size * 100 // total_size
            print(f"\r[WhisperNet] Скачивание: {min(pct, 100)}%", end='', flush=True)

    tmp_path = path + '.tmp'
    try:
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        # Таймаут 30 сек на соединение; скачиваем во временный файл
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            with open(tmp_path, 'wb') as f:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded * 100 // total
                        print(f"\r[WhisperNet] Скачивание: {pct}%", end='', flush=True)
        os.replace(tmp_path, path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise RuntimeError(
            f"Не удалось скачать модель Whisper ({model_name}).\n\n"
            f"Проверьте подключение к интернету и доступность huggingface.co.\n\n"
            f"Ошибка: {e}"
        ) from e
    print(f"\n[WhisperNet] Модель сохранена: {path}")
    return path


# ---------------------------------------------------------------------------
# WhisperNet backend — .NET 8 whisper.net + Vulkan
# ---------------------------------------------------------------------------

class WhisperNetBackend:
    """
    Запускает WhisperService.exe как долгоживущий subprocess.
    Общение по бинарному stdin/stdout протоколу:
      Python→C#: int32(len) + bytes(wav)
      C#→Python: int32(len) + bytes(text_utf8)
                 int32(-1) + int32(err_len) + bytes(err_utf8)  — при ошибке
    """

    def __init__(self, model_name: str, language: str):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._ready_event = threading.Event()
        self._ready_error: str | None = None
        self._language = language

        exe = self._find_service_exe()
        if not exe:
            raise RuntimeError("WhisperService.exe не найден")

        model_path = _ggml_model_path(model_name)
        self._exe = exe
        self._model_path = model_path

        print(f"[WhisperNet] Запуск сервиса: {exe}")
        self._proc = subprocess.Popen(
            [exe, model_path, language],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # stderr читается в отдельном потоке; он же сигнализирует о готовности
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

        # Ждём готовности (таймаут 60 сек — модель может долго грузиться)
        if not self._ready_event.wait(timeout=60):
            self._proc.kill()
            raise RuntimeError("WhisperService не вышел в Ready за 60 секунд")
        if self._ready_error:
            raise RuntimeError(f"WhisperService ошибка старта: {self._ready_error}")

    def _find_service_exe(self) -> str | None:
        # Базовые директории поиска
        dirs = []

        # При PyInstaller: sys.executable — это AI_Meetings.exe, рядом лежит whisper_service/
        dirs.append(os.path.dirname(sys.executable))

        # При запуске из исходников: рядом с main.py (sys.argv[0])
        dirs.append(os.path.dirname(os.path.abspath(sys.argv[0])))

        # data/whisper_service/ в репозитории (dev режим)
        dirs.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'whisper_service'))
        # Сам exe в data/whisper_service/ (поднимаемся через data/)
        dirs.append(os.path.dirname(os.path.dirname(__file__)))

        candidates = [
            os.path.join(d, 'whisper_service', 'WhisperService.exe') for d in dirs
        ] + [
            # data/whisper_service/WhisperService.exe (dev)
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'whisper_service', 'WhisperService.exe'),
        ]

        for p in candidates:
            if os.path.exists(p):
                print(f"[WhisperNet] Найден сервис: {p}")
                return p
        return None

    def _read_stderr(self):
        """Читает stderr в фоне, сигнализирует о готовности через _ready_event."""
        assert self._proc and self._proc.stderr
        try:
            for line in self._proc.stderr:
                msg = line.decode('utf-8', errors='replace').strip()
                if msg:
                    print(f"[WhisperNet] {msg}")
                if 'Ready' in msg:
                    self._ready_event.set()
                elif 'Fatal' in msg or 'not found' in msg.lower():
                    self._ready_error = msg
                    self._ready_event.set()
        except Exception:
            pass
        finally:
            # Если процесс упал до Ready — разблокируем ожидание
            if not self._ready_event.is_set():
                self._ready_error = "WhisperService завершился неожиданно"
                self._ready_event.set()

    def set_language(self, language: str):
        """Меняет язык распознавания. Перезапускает сервис если язык изменился."""
        lang = language or ''
        if lang == self._language:
            return
        print(f"[WhisperNet] Смена языка: '{self._language}' → '{lang}', перезапуск сервиса...")
        self._language = lang
        # Завершаем текущий процесс
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.stdin.write(struct.pack('<i', 0))
                self._proc.stdin.flush()
                self._proc.wait(timeout=3)
        except Exception:
            if self._proc:
                self._proc.kill()
        # Запускаем новый процесс с новым языком
        self._ready_event = threading.Event()
        self._ready_error = None
        self._proc = subprocess.Popen(
            [self._exe, self._model_path, lang],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()
        if not self._ready_event.wait(timeout=60):
            self._proc.kill()
            raise RuntimeError("WhisperService не вышел в Ready после смены языка")
        if self._ready_error:
            raise RuntimeError(f"WhisperService ошибка после смены языка: {self._ready_error}")

    def transcribe(self, wav_bytes: bytes) -> str:
        with self._lock:
            if not self._proc or self._proc.poll() is not None:
                raise RuntimeError("WhisperService не запущен")

            assert self._proc.stdin and self._proc.stdout

            # Отправляем: int32(len) + bytes
            self._proc.stdin.write(struct.pack('<i', len(wav_bytes)))
            self._proc.stdin.write(wav_bytes)
            self._proc.stdin.flush()

            # Читаем: int32(len)
            raw_len = self._proc.stdout.read(4)
            if len(raw_len) < 4:
                raise RuntimeError("WhisperService закрыл stdout")

            resp_len = struct.unpack('<i', raw_len)[0]

            if resp_len == -1:
                # Ошибка: читаем длину + текст ошибки
                err_raw = self._proc.stdout.read(4)
                err_len = struct.unpack('<i', err_raw)[0]
                err_bytes = self._proc.stdout.read(err_len)
                raise RuntimeError(f"WhisperService error: {err_bytes.decode('utf-8', errors='replace')}")

            text_bytes = self._proc.stdout.read(resp_len)
            return text_bytes.decode('utf-8', errors='replace')

    def close(self):
        if self._proc and self._proc.poll() is None:
            try:
                # Посылаем команду завершения: int32(0)
                self._proc.stdin.write(struct.pack('<i', 0))
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
        self._proc = None

    def __del__(self):
        self.close()


# ---------------------------------------------------------------------------
# faster-whisper fallback backend
# ---------------------------------------------------------------------------

def _select_ct2_device():
    try:
        import ctranslate2
        ctranslate2.get_supported_compute_types("cuda")
        print("CUDA доступна, используется GPU")
        return "cuda", "float16"
    except Exception:
        pass
    print("GPU (CUDA) недоступна, используется CPU")
    return "cpu", "int8"


class FasterWhisperBackend:
    def __init__(self, model_name: str, language: str):
        from faster_whisper import WhisperModel
        device, compute_type = _select_ct2_device()
        print(f"[FasterWhisper] Загрузка модели '{model_name}' (device={device}, compute={compute_type})...")

        # На Windows huggingface_hub создаёт symlinks, которые без Developer Mode
        # превращаются в 0-байтные файлы. Скачиваем модель напрямую без symlinks.
        model_path = self._ensure_model(model_name)
        self.model = WhisperModel(model_path, device=device, compute_type=compute_type)
        self.language = language
        print("[FasterWhisper] Модель загружена!")

    @staticmethod
    def _ensure_model(model_name: str) -> str:
        """Скачивает модель в локальную папку без symlinks и возвращает путь."""
        local_dir = os.path.join(
            os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
            'AI Meetings', 'models', f'faster-whisper-{model_name}'
        )
        marker = os.path.join(local_dir, 'model.bin')

        # Если модель уже скачана и файл не пустой — используем её
        if os.path.exists(marker) and os.path.getsize(marker) > 0:
            return local_dir

        print(f"[FasterWhisper] Скачивание модели Systran/faster-whisper-{model_name} (без symlinks)...")
        from huggingface_hub import snapshot_download
        # disable_tqdm удалён в huggingface_hub>=0.17; отключаем прогресс через env var
        # (актуально для GUI/--noconsole где stderr перенаправлен в DummyWriter)
        _prev_disable = os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS")
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        try:
            snapshot_download(
                repo_id=f"Systran/faster-whisper-{model_name}",
                local_dir=local_dir,
            )
        except Exception as e:
            # Если упало из-за записи в закрытый stdout/stderr или по сети
            print(f"[FasterWhisper] Ошибка при скачивании: {e}")
            if not os.path.exists(marker):
                raise
        finally:
            if _prev_disable is None:
                os.environ.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)
            else:
                os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = _prev_disable

        # Проверяем, что model.bin действительно скачался
        if not os.path.exists(marker) or os.path.getsize(marker) == 0:
            raise RuntimeError(
                f"Не удалось скачать модель faster-whisper-{model_name}.\n"
                "Проверьте подключение к интернету."
            )

        return local_dir

    def set_language(self, language: str):
        self.language = language

    NO_SPEECH_THRESHOLD = 0.6

    def transcribe(self, wav_bytes: bytes) -> str:
        temp_path = None
        try:
            temp_path = os.path.join(
                SPEECH_RECOGNITION['temp_dir'],
                f"whisper_{uuid.uuid4()}.wav"
            )
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(wav_bytes)

            kwargs = {"beam_size": 5}
            if self.language:
                kwargs["language"] = self.language

            segments_gen, _ = self.model.transcribe(temp_path, **kwargs)
            segments = list(segments_gen)

            if not segments:
                return ""

            total_dur = sum(max(s.end - s.start, 0) for s in segments)
            if total_dur > 0:
                weighted_no_speech = sum(
                    s.no_speech_prob * max(s.end - s.start, 0) for s in segments
                ) / total_dur
            else:
                weighted_no_speech = segments[0].no_speech_prob

            if weighted_no_speech > self.NO_SPEECH_THRESHOLD:
                print(f"[FasterWhisper] Сегмент отброшен (no_speech_prob={weighted_no_speech:.2f})")
                return ""

            return " ".join(s.text for s in segments).strip()
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def close(self):
        pass


# ---------------------------------------------------------------------------
# SpeechRecognizer — публичный API
# ---------------------------------------------------------------------------

class SpeechRecognizer:
    """
    Распознавание речи.
    Использует WhisperNet (whisper.net + Vulkan) если доступен,
    иначе падает на faster-whisper (CPU).
    """

    NO_SPEECH_THRESHOLD = 0.6

    def __init__(self, model_name=SPEECH_RECOGNITION['default_model']):
        self.model_name = model_name
        language = SPEECH_RECOGNITION['default_language']

        self._backend = None
        self._ensure_temp_dir()

        # Пробуем WhisperNet (GPU)
        try:
            self._backend = WhisperNetBackend(model_name, language)
            print("[SpeechRecognizer] Backend: WhisperNet (Vulkan GPU)")
        except Exception as e:
            print(f"[SpeechRecognizer] WhisperNet недоступен: {e} — fallback на faster-whisper")
            self._backend = FasterWhisperBackend(model_name, language)
            print("[SpeechRecognizer] Backend: faster-whisper (CPU)")

    def _ensure_temp_dir(self):
        temp_dir = SPEECH_RECOGNITION['temp_dir']
        try:
            os.makedirs(temp_dir, exist_ok=True)
        except Exception as e:
            print(f"[SpeechRecognizer] Не удалось создать temp-dir: {e}")

    def transcribe_audio_data(self, audio_data, sample_rate=16000,
                              language=SPEECH_RECOGNITION['default_language']) -> str:
        """
        Распознаёт речь из raw PCM bytes (16-bit, mono).
        language: 'ru', 'en', None/'auto' — None означает авто-определение.
        """
        try:
            if isinstance(audio_data, list):
                audio_data = b''.join(audio_data)

            if not audio_data:
                return ""

            # Фильтруем тишину по RMS (аналог no_speech_prob для WhisperNet)
            samples = np.frombuffer(audio_data, dtype=np.int16)
            rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
            if rms < 50:
                return ""

            # Пиковая нормализация: подтягиваем тихие/громкие записи к ~80% int16 range
            peak = float(np.max(np.abs(samples.astype(np.float32))))
            if peak > 0:
                target = 32767.0 * 0.8
                gain = min(target / peak, 8.0)  # не усиливаем больше чем в 8 раз
                if abs(gain - 1.0) > 0.05:  # применяем только если разница заметна
                    normalized = np.clip(samples.astype(np.float32) * gain, -32768, 32767).astype(np.int16)
                    audio_data = normalized.tobytes()

            # Передаём язык в backend перед транскрипцией
            effective_lang = language if language and language != 'auto' else None
            if self._backend and hasattr(self._backend, 'set_language'):
                self._backend.set_language(effective_lang or '')

            # Упаковываем в WAV в памяти
            wav_buf = self._to_wav_bytes(audio_data, sample_rate)
            text = self._backend.transcribe(wav_buf)

            if text:
                print(f"[SpeechRecognizer] Распознано: {text[:80]}{'...' if len(text) > 80 else ''}")
            return text

        except Exception as e:
            print(f"[SpeechRecognizer] Ошибка: {e}")
            traceback.print_exc()
            return ""

    @staticmethod
    def _to_wav_bytes(pcm_bytes: bytes, sample_rate: int) -> bytes:
        import io
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()

    def close(self):
        if self._backend:
            self._backend.close()
            self._backend = None

    def __del__(self):
        self.close()
