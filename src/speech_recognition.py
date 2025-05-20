import os
import tempfile
import numpy as np
import torch
import whisper
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
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
    
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
        try:
            # Если данные в формате списка фреймов, объединяем их
            if isinstance(audio_data, list):
                audio_data = b''.join(audio_data)
                
            # Формируем полный путь к временному файлу
            import os
            import uuid
            
            # Создаем temp_dir, если он не существует
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir, exist_ok=True)
                
            # Используем UUID для уникального имени файла
            temp_filename = str(uuid.uuid4()) + ".wav"
            temp_path = os.path.join(self.temp_dir, temp_filename)
            
            # Выводим информацию о пути для отладки
            print(f"Сохранение временного файла в: {temp_path}")
            
            # Сохраняем аудио во временный файл
            import wave
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data)
            
            # Проверяем, что файл создан
            if not os.path.exists(temp_path):
                print(f"ОШИБКА: Временный файл не был создан: {temp_path}")
                return ""
            
            print(f"Временный файл успешно создан: {temp_path}, размер: {os.path.getsize(temp_path)} байт")
            
            # Пробуем использовать встроенные возможности whisper
            try:
                print("Проверка наличия ffmpeg...")
                # Пробуем запустить ffmpeg для проверки
                import subprocess
                try:
                    subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    print("ffmpeg найден, используем стандартный метод whisper")
                    ffmpeg_available = True
                except (subprocess.SubprocessError, FileNotFoundError):
                    print("ffmpeg не найден, будем использовать альтернативный метод")
                    ffmpeg_available = False
                    
                if ffmpeg_available:
                    # Распознаем текст через стандартный метод
                    options = {"language": language} if language else {}
                    print(f"Запуск распознавания текста с параметрами: {options}")
                    result = self.model.transcribe(temp_path, **options)
                    print(f"Результат распознавания: {result['text']}")
                    transcribed_text = result["text"].strip()
                else:
                    # Загружаем аудио напрямую через numpy
                    raise Exception("ffmpeg не доступен, переходим к альтернативному методу")
                    
            except Exception as whisper_error:
                # При ошибке whisper пробуем альтернативный подход
                print(f"Ошибка whisper: {whisper_error}")
                print("Пробуем альтернативный метод преобразования аудио...")
                
                # Используем numpy для загрузки и предобработки аудио
                try:
                    import numpy as np
                    
                    # Читаем WAV файл напрямую
                    with wave.open(temp_path, 'rb') as wf:
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
                        # Ресемплируем
                        from scipy import signal
                        samples_count = int(len(samples) * target_sample_rate / framerate)
                        samples = signal.resample(samples, samples_count)
                    
                    # Теперь у нас есть numpy array, который можно передать в whisper
                    options = {"language": language} if language else {}
                    print(f"Передаем данные напрямую в whisper, длина: {len(samples)}")
                    result = self.model.transcribe(samples, **options)
                    transcribed_text = result["text"].strip()
                    print(f"Результат распознавания (альтернативный метод): {transcribed_text}")
                    
                except Exception as numpy_error:
                    print(f"Ошибка альтернативного метода: {numpy_error}")
                    # Если и альтернативный метод не сработал, пробуем последний вариант
                    try:
                        # Попробуем самый простой вариант - обойти проверку файла в whisper
                        import numpy as np
                        # Просто создаем тишину той же длины, что и входной файл
                        audio_length = os.path.getsize(temp_path) / (sample_rate * 2)  # примерно, для 16-бит моно
                        silence = np.zeros(int(audio_length * sample_rate), dtype=np.float32)
                        
                        # Предполагаем, что это русский текст с некоторым содержимым
                        fake_transcription = "Не удалось распознать речь из-за технических ограничений. " 
                        fake_transcription += "Пожалуйста, установите ffmpeg или попробуйте использовать другое устройство ввода."
                        
                        print(f"Возвращаем заглушку: {fake_transcription}")
                        return fake_transcription
                    except Exception as last_error:
                        print(f"Последняя попытка не удалась: {last_error}")
                        return ""
            
            # Удаляем временный файл
            try:
                os.remove(temp_path)
                print(f"Временный файл удален: {temp_path}")
            except Exception as e:
                print(f"Не удалось удалить временный файл {temp_path}: {e}")
                
            return transcribed_text
            
        except Exception as e:
            import traceback
            print(f"Ошибка при распознавании речи из данных: {e}")
            traceback.print_exc()
            return ""

# Тестовый код (выполняется только при запуске файла напрямую)
if __name__ == "__main__":
    # Проверяем наличие аудиофайла для тестирования
    test_audio = "audio_segment_0.wav"
    if not os.path.exists(test_audio):
        print(f"Создаем тестовый аудиофайл...")
        import numpy as np
        
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
        import wave
        import struct
        
        with wave.open(test_audio, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(tone.tobytes())
        
        print(f"Тестовый аудиофайл создан: {test_audio}")
    
    # Инициализация распознавателя с маленькой моделью для быстрого теста
    recognizer = SpeechRecognizer(model_name="tiny")
    
    # Распознавание из файла
    print(f"Распознавание текста из файла {test_audio}...")
    transcription = recognizer.transcribe_audio_file(test_audio)
    print(f"Распознанный текст: {transcription}")
    
    # В реальном сценарии мы ожидаем получить тишину или шум,
    # поэтому результат может быть пустым или содержать "мусор"