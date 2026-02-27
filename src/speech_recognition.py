import os
import tempfile
import numpy as np
import wave
import subprocess
import uuid
import traceback
from faster_whisper import WhisperModel
from utils.config import SPEECH_RECOGNITION


def _select_device():
    """
    Выбирает устройство для инференса.
    Возвращает (device, compute_type).
    На Windows с AMD/без NVIDIA всегда возвращает cpu/int8.
    """
    try:
        import ctranslate2
        ctranslate2.get_supported_compute_types("cuda")
        # Если не упало — CUDA доступна
        print("CUDA доступна, используется GPU")
        return "cuda", "float16"
    except Exception:
        pass
    print("GPU (CUDA) недоступна, используется CPU")
    return "cpu", "int8"


class SpeechRecognizer:
    """
    Класс для распознавания речи с использованием faster-whisper.
    faster-whisper работает в 2-4x быстрее openai-whisper на CPU,
    не требует torch и поддерживает int8-квантизацию.
    """

    # Если вероятность отсутствия речи выше этого порога — отбрасываем сегмент.
    NO_SPEECH_THRESHOLD = 0.6

    def __init__(self, model_name=SPEECH_RECOGNITION['default_model']):
        device, compute_type = _select_device()
        self.device = device
        self.model_name = model_name

        print(f"Загрузка модели Whisper '{model_name}' (faster-whisper, device={device}, compute={compute_type})...")
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        print("Модель загружена!")

        # Создаем директорию для временных файлов
        self.temp_dir = SPEECH_RECOGNITION['temp_dir']
        self._ensure_temp_dir()

        # Проверяем доступность ffmpeg при инициализации
        self.ffmpeg_available = self._check_ffmpeg()

    def _ensure_temp_dir(self):
        try:
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir, exist_ok=True)
                print(f"Создана директория для временных файлов: {self.temp_dir}")
        except Exception as e:
            print(f"Ошибка при создании директории {self.temp_dir}: {e}")
            self.temp_dir = tempfile.gettempdir()
            print(f"Используется системная временная директория: {self.temp_dir}")

    def _check_ffmpeg(self):
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            if result.returncode == 0:
                print("FFmpeg найден и доступен")
                return True
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
            print(f"FFmpeg не доступен: {e}")
        return False

    def transcribe_audio_data(self, audio_data, sample_rate=16000, language=SPEECH_RECOGNITION['default_language']):
        """
        Распознает речь из аудиоданных в памяти (bytes или list of bytes).

        Returns:
            str: Распознанный текст
        """
        temp_path = None
        try:
            if isinstance(audio_data, list):
                audio_data = b''.join(audio_data)

            if not audio_data or len(audio_data) == 0:
                print("Нет данных для распознавания")
                return ""

            temp_filename = f"whisper_{str(uuid.uuid4())}.wav"
            temp_path = os.path.join(self.temp_dir, temp_filename)

            print(f"Сохранение временного файла: {temp_path}")
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data)

            if not os.path.exists(temp_path):
                print(f"ОШИБКА: Временный файл не был создан: {temp_path}")
                return ""

            file_size = os.path.getsize(temp_path)
            if file_size == 0:
                print(f"ПРЕДУПРЕЖДЕНИЕ: Временный файл пустой: {temp_path}")
                return ""

            print(f"Временный файл создан: {temp_path}, размер: {file_size} байт")
            return self._transcribe_with_whisper(temp_path, language)

        except Exception as e:
            print(f"Ошибка при распознавании речи: {e}")
            traceback.print_exc()
            return ""
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"Временный файл удален: {temp_path}")
                except Exception as e:
                    print(f"Не удалось удалить временный файл {temp_path}: {e}")

    def _transcribe_with_whisper(self, audio_path, language=None):
        """
        Выполняет распознавание через faster-whisper.
        Фильтрует сегменты с высокой вероятностью отсутствия речи.

        Returns:
            str: Распознанный текст или "" если речь не обнаружена
        """
        try:
            kwargs = {"beam_size": 5}
            if language:
                kwargs["language"] = language

            segments_gen, info = self.model.transcribe(audio_path, **kwargs)

            # Собираем сегменты и считаем взвешенный no_speech_prob
            segments = list(segments_gen)

            if not segments:
                return ""

            total_dur = sum(max(s.end - s.start, 0) for s in segments)
            if total_dur > 0:
                weighted_no_speech = sum(
                    s.no_speech_prob * max(s.end - s.start, 0)
                    for s in segments
                ) / total_dur
            else:
                weighted_no_speech = segments[0].no_speech_prob

            if weighted_no_speech > self.NO_SPEECH_THRESHOLD:
                print(f"Сегмент отброшен (no_speech_prob={weighted_no_speech:.2f})")
                return ""

            text = " ".join(s.text for s in segments).strip()
            if text:
                print(f"Распознано: {text[:80]}{'...' if len(text) > 80 else ''}")
            return text

        except Exception as e:
            print(f"Ошибка при распознавании с Whisper: {e}")
            traceback.print_exc()
            return ""


# Тестовый код (выполняется только при запуске файла напрямую)
if __name__ == "__main__":
    test_audio = "test_audio.wav"
    if not os.path.exists(test_audio):
        print("Создаем тестовый аудиофайл...")
        sample_rate = 16000
        duration = 3
        frequency = 440
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        tone = np.sin(2 * np.pi * frequency * t)
        tone = (tone * 32767).astype(np.int16)
        with wave.open(test_audio, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(tone.tobytes())
        print(f"Тестовый аудиофайл создан: {test_audio}")

    recognizer = SpeechRecognizer(model_name="tiny")
    print(f"\nРаспознавание текста из файла {test_audio}...")
    transcription = recognizer.transcribe_audio_file(test_audio)
    print(f"Распознанный текст: {transcription}")

    if os.path.exists(test_audio):
        os.remove(test_audio)
        print(f"\nТестовый файл удален: {test_audio}")
