import sounddevice as sd
import threading
import time
import numpy as np
from queue import Queue
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

        # Если Stereo Mix не найден — запускаем генератор тишины
        print("Stereo Mix не найден. Захват системного звука недоступен.")
        print("Включите Stereo Mix в настройках звука Windows или установите VB-Cable.")
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
    
    def stop_recording(self):
        """
        Останавливает запись
        """
        self.is_recording = False
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