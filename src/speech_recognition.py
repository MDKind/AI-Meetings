import os
import tempfile
import numpy as np
import torch
import whisper
import wave
import subprocess
import uuid
import traceback
from utils.config import SPEECH_RECOGNITION

class SpeechRecognizer:
    """
    Класс для распознавания речи с использованием Whisper от OpenAI
    """
    def __init__(self, model_name=SPEECH_RECOGNITION['default_model']):
        """
        Инициализирует распознаватель речи с моделью Whisper
        
        Args:
            model_name (str): Размер модели ("tiny", "base", "small", "medium", "large")
        """
        print(f"Загрузка модели Whisper '{model_name}'...")
        self.model = whisper.load_model(model_name)
        print("Модель загружена!")
        
        # Сохраняем имя модели как отдельное свойство
        self.model_name = model_name
        
        # Проверка наличия GPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Используется устройство: {self.device}")
        
        if self.device == "cuda":
            self.model = self.model.to(self.device)
            
        # Создаем директорию для временных файлов
        self.temp_dir = SPEECH_RECOGNITION['temp_dir']
        self._ensure_temp_dir()
        
        # Проверяем доступность ffmpeg при инициализации
        self.ffmpeg_available = self._check_ffmpeg()
    
    def _ensure_temp_dir(self):
        """Убеждаемся, что директория для временных файлов существует"""
        try:
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir, exist_ok=True)
                print(f"Создана директория для временных файлов: {self.temp_dir}")
        except Exception as e:
            print(f"Ошибка при создании директории {self.temp_dir}: {e}")
            # Используем системную временную директорию
            self.temp_dir = tempfile.gettempdir()
            print(f"Используется системная временная директория: {self.temp_dir}")
    
    def _check_ffmpeg(self):
        """Проверяет доступность ffmpeg"""
        try:
            # Убираем capture_output=True, так как мы уже указываем stdout и stderr
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
        Распознает речь из аудиоданных в памяти
        
        Args:
            audio_data: Аудиоданные в формате numpy array или байтов
            sample_rate (int): Частота дискретизации аудио
            language (str): Язык аудио (None для автоопределения)
            
        Returns:
            str: Распознанный текст
        """
        temp_path = None
        try:
            # Если данные в формате списка фреймов, объединяем их
            if isinstance(audio_data, list):
                audio_data = b''.join(audio_data)
            
            # Проверяем, что есть данные для обработки
            if not audio_data or len(audio_data) == 0:
                print("Нет данных для распознавания")
                return ""
            
            # Создаем временный файл
            temp_filename = f"whisper_{str(uuid.uuid4())}.wav"
            temp_path = os.path.join(self.temp_dir, temp_filename)
            
            # Сохраняем аудио во временный файл
            print(f"Сохранение временного файла: {temp_path}")
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data)
            
            # Проверяем, что файл создан и не пустой
            if not os.path.exists(temp_path):
                print(f"ОШИБКА: Временный файл не был создан: {temp_path}")
                return ""
            
            file_size = os.path.getsize(temp_path)
            if file_size == 0:
                print(f"ПРЕДУПРЕЖДЕНИЕ: Временный файл пустой: {temp_path}")
                return ""
            
            print(f"Временный файл создан: {temp_path}, размер: {file_size} байт")
            
            # Пробуем распознать с помощью Whisper
            transcribed_text = self._transcribe_with_whisper(temp_path, language)
            
            return transcribed_text
            
        except Exception as e:
            print(f"Ошибка при распознавании речи: {e}")
            traceback.print_exc()
            return ""
        finally:
            # Удаляем временный файл
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"Временный файл удален: {temp_path}")
                except Exception as e:
                    print(f"Не удалось удалить временный файл {temp_path}: {e}")
    
    # Если вероятность отсутствия речи выше этого порога — отбрасываем сегмент.
    # Устраняет «галлюцинации» Whisper на тишине/шуме.
    NO_SPEECH_THRESHOLD = 0.6

    def _transcribe_with_whisper(self, audio_path, language=None):
        """
        Выполняет распознавание с помощью Whisper.
        Фильтрует сегменты с высокой вероятностью отсутствия речи (no_speech_prob).

        Args:
            audio_path: Путь к аудиофайлу
            language: Язык для распознавания

        Returns:
            str: Распознанный текст или "" если речь не обнаружена
        """
        try:
            options = {}
            if language:
                options["language"] = language

            if self.ffmpeg_available:
                result = self.model.transcribe(audio_path, **options)
            else:
                return self._transcribe_without_ffmpeg(audio_path, language)

            # Фильтр галлюцинаций: проверяем no_speech_prob по всем сегментам
            segments = result.get("segments", [])
            if segments:
                # Берём взвешенное среднее: длинные сегменты важнее
                total_dur = sum(s.get("end", 0) - s.get("start", 0) for s in segments)
                if total_dur > 0:
                    weighted_no_speech = sum(
                        s.get("no_speech_prob", 0) * (s.get("end", 0) - s.get("start", 0))
                        for s in segments
                    ) / total_dur
                else:
                    weighted_no_speech = segments[0].get("no_speech_prob", 0)

                if weighted_no_speech > self.NO_SPEECH_THRESHOLD:
                    print(f"Сегмент отброшен (no_speech_prob={weighted_no_speech:.2f})")
                    return ""

            text = result["text"].strip()
            if text:
                print(f"Распознано: {text[:80]}{'...' if len(text) > 80 else ''}")
            return text

        except Exception as e:
            print(f"Ошибка при распознавании с Whisper: {e}")
            return self._transcribe_without_ffmpeg(audio_path, language)
    
    def _transcribe_without_ffmpeg(self, audio_path, language=None):
        """
        Альтернативный метод распознавания без использования ffmpeg
        
        Args:
            audio_path: Путь к аудиофайлу
            language: Язык для распознавания
            
        Returns:
            str: Распознанный текст
        """
        try:
            # Читаем WAV файл напрямую
            with wave.open(audio_path, 'rb') as wf:
                n_frames = wf.getnframes()
                audio_bytes = wf.readframes(n_frames)
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
            
            # Преобразуем байты в numpy array
            if sampwidth == 2:  # 16-bit
                dtype = np.int16
            elif sampwidth == 4:  # 32-bit
                dtype = np.int32
            else:
                dtype = np.uint8
            
            # Интерпретируем байты как числа
            samples = np.frombuffer(audio_bytes, dtype=dtype)
            
            # Если стерео, преобразуем в моно
            if n_channels > 1:
                samples = samples.reshape((-1, n_channels)).mean(axis=1)
            
            # Нормализуем до float32 в диапазоне [-1, 1]
            samples = samples.astype(np.float32) / (2**(sampwidth*8-1))
            
            # Приводим к правильной частоте дискретизации, если нужно
            target_sample_rate = 16000
            if framerate != target_sample_rate:
                # Простая интерполяция для изменения частоты дискретизации
                # Это не идеально, но работает без scipy
                samples_count = int(len(samples) * target_sample_rate / framerate)
                x_old = np.linspace(0, len(samples) - 1, len(samples))
                x_new = np.linspace(0, len(samples) - 1, samples_count)
                samples = np.interp(x_new, x_old, samples)
            
            # Теперь у нас есть numpy array, который можно передать в whisper
            options = {}
            if language:
                options["language"] = language
                
            print(f"Передаем данные напрямую в whisper, длина: {len(samples)}")
            result = self.model.transcribe(samples, **options)
            text = result["text"].strip()
            print(f"Распознанный текст (альтернативный метод): {text}")
            return text
            
        except Exception as e:
            print(f"Ошибка альтернативного метода: {e}")
            return ""
    
    def transcribe_audio_file(self, file_path, language=None):
        """
        Распознает речь из аудиофайла
        
        Args:
            file_path: Путь к аудиофайлу
            language: Язык для распознавания
            
        Returns:
            str: Распознанный текст
        """
        try:
            # Читаем файл и передаем данные в transcribe_audio_data
            with open(file_path, 'rb') as f:
                audio_data = f.read()
            return self.transcribe_audio_data(audio_data, language=language)
        except Exception as e:
            print(f"Ошибка при чтении файла {file_path}: {e}")
            return ""


# Тестовый код (выполняется только при запуске файла напрямую)
if __name__ == "__main__":
    # Проверяем наличие аудиофайла для тестирования
    test_audio = "test_audio.wav"
    if not os.path.exists(test_audio):
        print(f"Создаем тестовый аудиофайл...")
        
        # Создаем синусоидальный тон для теста
        sample_rate = 16000
        duration = 3  # в секундах
        frequency = 440  # частота тона (Ля 440 Гц)
        
        # Генерируем синусоидальный сигнал
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        tone = np.sin(2 * np.pi * frequency * t)
        
        # Нормализуем до 16-бит PCM
        tone = (tone * 32767).astype(np.int16)
        
        # Сохраняем в WAV файл
        with wave.open(test_audio, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(tone.tobytes())
        
        print(f"Тестовый аудиофайл создан: {test_audio}")
    
    # Инициализация распознавателя с маленькой моделью для быстрого теста
    recognizer = SpeechRecognizer(model_name="tiny")
    
    # Распознавание из файла
    print(f"\nРаспознавание текста из файла {test_audio}...")
    transcription = recognizer.transcribe_audio_file(test_audio)
    print(f"Распознанный текст: {transcription}")
    
    # Очистка
    if os.path.exists(test_audio):
        os.remove(test_audio)
        print(f"\nТестовый файл удален: {test_audio}")
