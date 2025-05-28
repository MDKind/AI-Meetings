import sounddevice as sd
import wave
import threading
import time
import numpy as np
from queue import Queue
import os
import platform

class SystemAudioCapture:
    """
    Альтернативная реализация захвата системного звука
    с использованием доступных API для различных платформ
    """
    def __init__(self, sample_rate=16000, channels=1, chunk_size=1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.is_recording = False
        self.data_queue = Queue()
        self.system = platform.system()
        
    def start_recording(self, device_index=None):
        """
        Начинает запись системного звука с использованием
        наиболее подходящего метода для текущей системы
        
        Args:
            device_index: Индекс устройства вывода
        """
        self.is_recording = True
        self.data_queue = Queue()
        
        # Пробуем подход с приоритетом на альтернативные методы
        print("Запуск универсального захвата системного звука...")
        
        # Сначала попробуем найти Stereo Mix
        stereo_mix_found = False
        stereo_mix_index = None
        
        try:
            devices = sd.query_devices()
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    name = device['name'].lower()
                    if ("stereo mix" in name or "стереомикшер" in name or 
                        "what u hear" in name or "cable output" in name):
                        stereo_mix_found = True
                        stereo_mix_index = i
                        print(f"Найдено устройство для захвата системного звука: {device['name']} (индекс {i})")
                        break
        except Exception as e:
            print(f"Ошибка при поиске Stereo Mix: {e}")
        
        # Если нашли Stereo Mix, используем его
        if stereo_mix_found and stereo_mix_index is not None:
            try:
                print(f"Попытка записи через Stereo Mix (индекс {stereo_mix_index})...")
                self._record_with_sounddevice(stereo_mix_index)
                return
            except Exception as e:
                print(f"Ошибка при использовании Stereo Mix: {e}")
        
        # Если Stereo Mix не найден или не работает, попробуем PyAudio
        try:
            print("Попытка использования PyAudio для захвата системного звука...")
            self._record_with_pyaudio(device_index)
            return
        except Exception as e:
            print(f"Ошибка при использовании PyAudio: {e}")
            
        # В крайнем случае пробуем использовать ffmpeg
        try:
            print("Попытка использования ffmpeg для захвата системного звука...")
            self._record_with_ffmpeg()
            return
        except Exception as e:
            print(f"Ошибка при использовании ffmpeg: {e}")
        
        # Если ни один метод не работает, сообщаем об этом
        print("Не удалось найти работающий метод захвата системного звука.")
        print("Рекомендации:")
        print("1. Установите PyAudio: pip install pyaudio")
        print("2. Установите ffmpeg, запустив install_audio_deps.bat в корневой директории проекта")
        print("3. Включите Stereo Mix в настройках звука Windows")
        print("4. Установите виртуальное аудио устройство типа VB-Cable")
        
        # Создадим генератор тишины, чтобы приложение могло продолжать работать
        print("Создание генератора тишины для продолжения работы...")
        threading.Thread(target=self._generate_silence, daemon=True).start()
    
    def _generate_silence(self):
        """
        Генерирует тишину для обеспечения продолжения работы приложения
        при отсутствии возможности захвата системного звука
        """
        print("Генератор тишины запущен. Захват системного звука недоступен.")
        
        # Создаем массив тишины для демонстрационных целей
        silence = np.zeros((self.chunk_size, self.channels), dtype=np.float32)
        
        # Регулярно отправляем тишину в очередь
        while self.is_recording:
            time.sleep(0.5)  # Отправляем тишину каждые 500 мс
            self.data_queue.put(silence.copy())
    
    def _record_windows(self, device_index):
        """
        Запись системного звука в Windows с использованием PyAudio или ffmpeg
        """
        print("Запуск специализированного захвата системного звука для Windows...")
        
        # Пробуем найти Stereo Mix или аналогичное устройство
        found_stereo_mix = False
        stereo_mix_index = None
        
        try:
            devices = sd.query_devices()
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    name = device['name'].lower()
                    if ("stereo mix" in name or "стереомикшер" in name or 
                        "what u hear" in name or "cable output" in name):
                        found_stereo_mix = True
                        stereo_mix_index = i
                        print(f"Найдено устройство для захвата системного звука: {device['name']} (индекс {i})")
                        break
        except Exception as e:
            print(f"Ошибка при поиске Stereo Mix: {e}")
        
        if found_stereo_mix and stereo_mix_index is not None:
            # Используем Stereo Mix через sounddevice
            self._record_with_sounddevice(stereo_mix_index)
        else:
            # Пробуем PyAudio
            try:
                self._record_with_pyaudio(device_index)
            except Exception as e:
                print(f"Ошибка при использовании PyAudio: {e}")
                # В крайнем случае используем ffmpeg
                self._record_with_ffmpeg()
    
    def _record_with_sounddevice(self, device_index):
        """
        Запись с использованием sounddevice
        """
        print(f"Попытка записи с устройства {device_index} через sounddevice...")
        
        try:
            def callback(indata, frames, time, status):
                if status:
                    print(f"Статус: {status}")
                self.data_queue.put(indata.copy())
            
            with sd.InputStream(
                device=device_index,
                channels=self.channels,
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                callback=callback
            ):
                print(f"Запись системного звука через sounddevice началась...")
                while self.is_recording:
                    time.sleep(0.1)
                    
        except Exception as e:
            print(f"Ошибка при записи через sounddevice: {e}")
            raise
    
    def _record_with_pyaudio(self, device_index):
        """
        Запись с использованием PyAudio
        """
        print("Попытка записи через PyAudio...")
        
        try:
            import pyaudio
            
            p = pyaudio.PyAudio()
            
            # Ищем подходящее устройство, если индекс не указан
            if device_index is None:
                for i in range(p.get_device_count()):
                    device_info = p.get_device_info_by_index(i)
                    if (device_info['maxInputChannels'] > 0 and 
                        ('stereo mix' in device_info['name'].lower() or 
                         'стереомикшер' in device_info['name'].lower() or
                         'what u hear' in device_info['name'].lower() or
                         'cable output' in device_info['name'].lower())):
                        device_index = i
                        print(f"Найдено устройство для захвата системного звука: {device_info['name']} (индекс {i})")
                        break
            
            # Если не нашли Stereo Mix, пробуем любое входное устройство
            if device_index is None:
                for i in range(p.get_device_count()):
                    device_info = p.get_device_info_by_index(i)
                    if device_info['maxInputChannels'] > 0:
                        device_index = i
                        print(f"Используем устройство ввода: {device_info['name']} (индекс {i})")
                        break
            
            if device_index is None:
                raise Exception("Не найдено подходящих устройств ввода")
            
            # Открываем поток для записи
            stream = p.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size
            )
            
            print(f"Запись системного звука через PyAudio началась с устройства {device_index}...")
            
            # Чтение данных из потока
            while self.is_recording:
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                audio_data = np.frombuffer(data, dtype=np.int16)
                # Конвертация в формат float32 для совместимости с sounddevice
                audio_data = audio_data.astype(np.float32) / 32767.0
                audio_data = audio_data.reshape(-1, self.channels)
                self.data_queue.put(audio_data)
            
            # Закрываем ресурсы
            stream.stop_stream()
            stream.close()
            p.terminate()
            
        except ImportError:
            print("PyAudio не установлен, переключаемся на другой метод...")
            raise
        except Exception as e:
            print(f"Ошибка при записи через PyAudio: {e}")
            raise
    
    def _record_with_ffmpeg(self):
        """
        Запись системного звука с использованием ffmpeg
        """
        print("Попытка записи системного звука через ffmpeg...")
        
        try:
            import subprocess
            import tempfile
            
            # Создаем временный файл для вывода ffmpeg
            temp_dir = tempfile.gettempdir()
            temp_file = os.path.join(temp_dir, "system_audio_capture.wav")
            
            # Команда ffmpeg для захвата системного звука
            if self.system == "Windows":
                # Для Windows используем устройство dshow
                cmd = [
                    "ffmpeg", "-f", "dshow", "-i", "audio=virtual-audio-capturer",
                    "-acodec", "pcm_s16le", "-ar", str(self.sample_rate), 
                    "-ac", str(self.channels), "-y", temp_file
                ]
            elif self.system == "Darwin":  # macOS
                # Для macOS используем устройство avfoundation
                cmd = [
                    "ffmpeg", "-f", "avfoundation", "-i", ":0",
                    "-acodec", "pcm_s16le", "-ar", str(self.sample_rate), 
                    "-ac", str(self.channels), "-y", temp_file
                ]
            else:  # Linux
                # Для Linux используем устройство pulse
                cmd = [
                    "ffmpeg", "-f", "pulse", "-i", "default",
                    "-acodec", "pcm_s16le", "-ar", str(self.sample_rate), 
                    "-ac", str(self.channels), "-y", temp_file
                ]
            
            # Запускаем ffmpeg в фоновом режиме
            self.ffmpeg_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            
            print("Запись системного звука через ffmpeg началась...")
            
            # Ждем, пока запись активна
            start_time = time.time()
            while self.is_recording:
                time.sleep(0.5)
                
                # Каждые 2 секунды проверяем и читаем записанные данные
                if (time.time() - start_time) > 2:
                    try:
                        # Читаем записанные данные
                        with wave.open(temp_file, 'rb') as wf:
                            frames = wf.getnframes()
                            audio_data = np.frombuffer(
                                wf.readframes(frames), 
                                dtype=np.int16
                            )
                            # Конвертация в формат float32
                            audio_data = audio_data.astype(np.float32) / 32767.0
                            audio_data = audio_data.reshape(-1, self.channels)
                            self.data_queue.put(audio_data)
                    except Exception as e:
                        print(f"Ошибка при чтении записанных данных: {e}")
                    
                    start_time = time.time()
            
            # Завершаем процесс ffmpeg
            if self.ffmpeg_process:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process = None
                
            # Очистка временного файла
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
                
        except Exception as e:
            print(f"Ошибка при записи через ffmpeg: {e}")
            raise
    
    def _record_generic(self, device_index):
        """
        Общий метод записи для других платформ
        """
        print(f"Запуск стандартного захвата системного звука...")
        
        try:
            self._record_with_sounddevice(device_index)
        except Exception as e:
            print(f"Ошибка при стандартном захвате: {e}")
            try:
                self._record_with_pyaudio(device_index)
            except Exception as e:
                print(f"Ошибка при использовании PyAudio: {e}")
                self._record_with_ffmpeg()
    
    def stop_recording(self):
        """
        Останавливает запись
        """
        self.is_recording = False
        
        # Останавливаем ffmpeg, если он запущен
        if hasattr(self, 'ffmpeg_process') and self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process = None
            except:
                pass
        
        print("Запись системного звука остановлена.")
    
    def get_audio_data(self):
        """
        Получает накопленные аудиоданные из очереди
        
        Returns:
            numpy.ndarray: Аудиоданные в формате numpy array
            или None, если данных нет
        """
        if self.data_queue.empty():
            return None
        
        chunks = []
        while not self.data_queue.empty():
            chunks.append(self.data_queue.get())
            
        if chunks:
            return np.concatenate(chunks)
        
        return None