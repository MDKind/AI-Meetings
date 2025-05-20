import sounddevice as sd
import numpy as np
import threading
import time
import queue
from utils.config import AUDIO_SETTINGS

class RealTimeAudioProcessor:
    """
    Класс для обработки аудио в реальном времени из наушников/микрофона
    """
    def __init__(self, 
                 chunk_size=AUDIO_SETTINGS['chunk_size'], 
                 channels=AUDIO_SETTINGS['channels'], 
                 rate=AUDIO_SETTINGS['rate'],
                 silence_threshold=AUDIO_SETTINGS['silence_threshold'],
                 buffer_duration=10):  # Буфер на 10 секунд
        """
        Инициализирует процессор аудио
        
        Args:
            chunk_size (int): Размер чанка аудио
            channels (int): Количество каналов
            rate (int): Частота дискретизации
            silence_threshold (int): Порог тишины
            buffer_duration (int): Длительность буфера в секундах
        """
        self.chunk_size = chunk_size
        self.channels = channels
        self.rate = rate
        self.silence_threshold = silence_threshold
        
        # Максимальный размер буфера (в чанках)
        self.buffer_size = int(buffer_duration * rate / chunk_size)
        
        # Кольцевой буфер для хранения последних N секунд аудио
        self.audio_buffer = []
        
        # Очередь для обработанных сегментов
        self.segment_queue = queue.Queue()
        
        # Флаги состояния
        self.is_processing = False
        self.stream = None
        
        # Параметры детектирования речи
        self.silence_duration = AUDIO_SETTINGS['silence_duration']
        self.silent_chunks = 0
        self.speaking = False
        self.current_segment = []
        
        # Колбэк для обработки сегментов
        self.on_segment_ready = None
    
    def start_processing(self, device_index=None, on_segment_ready=None):
        """
        Запускает обработку аудио в реальном времени
        
        Args:
            device_index (int): Индекс устройства ввода
            on_segment_ready (callable): Функция обратного вызова, вызываемая при готовности сегмента
        """
        if self.is_processing:
            print("Обработка уже запущена")
            return False
        
        self.on_segment_ready = on_segment_ready
        self.is_processing = True
        self.audio_buffer = []
        self.current_segment = []
        self.silent_chunks = 0
        self.speaking = False
        
        try:
            # Создаем поток ввода аудио
            self.stream = sd.InputStream(
                samplerate=self.rate,
                channels=self.channels,
                device=device_index,
                blocksize=self.chunk_size,
                dtype='float32',
                callback=self._audio_callback
            )
            
            # Запускаем поток
            self.stream.start()
            
            # Запускаем отдельный поток для обработки сегментов
            self.processing_thread = threading.Thread(target=self._process_segments)
            self.processing_thread.daemon = True
            self.processing_thread.start()
            
            print(f"Запущена обработка аудио с устройства {device_index}")
            return True
            
        except Exception as e:
            print(f"Ошибка при запуске обработки аудио: {e}")
            self.is_processing = False
            return False
    
    def stop_processing(self):
        """
        Останавливает обработку аудио
        """
        if not self.is_processing:
            return
        
        # Устанавливаем флаг остановки
        self.is_processing = False
        
        # Останавливаем и закрываем поток
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        # Добавляем оставшийся сегмент в очередь, если он не пустой
        if self.current_segment:
            self.segment_queue.put(self.current_segment.copy())
            self.current_segment = []
        
        print("Обработка аудио остановлена")
    
    def _audio_callback(self, indata, frames, time_info, status):
        """
        Функция обратного вызова для обработки аудио
        
        Args:
            indata: Входные данные аудио
            frames: Количество фреймов
            time_info: Информация о времени
            status: Статус
        """
        if status:
            print(f"Статус аудио: {status}")
        
        # Конвертируем в int16 для определения громкости
        audio_data = (indata * 32767).astype(np.int16)
        
        # Получаем байтовое представление
        data = audio_data.tobytes()
        
        # Добавляем в буфер
        self.audio_buffer.append(data)
        
        # Ограничиваем размер буфера
        if len(self.audio_buffer) > self.buffer_size:
            self.audio_buffer.pop(0)
        
        # Определяем громкость
        volume = np.abs(audio_data).mean()
        
        # Детектируем речь
        if volume > self.silence_threshold:
            self.silent_chunks = 0
            
            if not self.speaking:
                self.speaking = True
                # print("Речь начата")
                
                # Добавляем часть буфера для контекста
                buffer_context_size = min(int(self.rate / self.chunk_size), len(self.audio_buffer))
                for i in range(buffer_context_size):
                    idx = len(self.audio_buffer) - buffer_context_size + i
                    if idx >= 0:
                        self.current_segment.append(self.audio_buffer[idx])
            
            self.current_segment.append(data)
        else:
            self.silent_chunks += 1
            
            # Если речь закончилась и есть данные для обработки
            if self.speaking and self.silent_chunks > int(self.rate / self.chunk_size * self.silence_duration):
                self.speaking = False
                
                if self.current_segment:
                    # Добавляем сегмент в очередь
                    self.segment_queue.put(self.current_segment.copy())
                    # print(f"Сегмент речи добавлен в очередь (длина: {len(self.current_segment)} чанков)")
                    self.current_segment = []
            
            # Если все еще говорят, продолжаем записывать тишину (для контекста)
            elif self.speaking:
                self.current_segment.append(data)
    
    def _process_segments(self):
        """
        Обрабатывает сегменты из очереди
        """
        while self.is_processing:
            try:
                # Проверяем очередь с таймаутом
                segment = self.segment_queue.get(timeout=0.5)
                
                # Если есть колбэк, вызываем его с сегментом
                if self.on_segment_ready:
                    self.on_segment_ready(segment)
                
                # Помечаем задачу как выполненную
                self.segment_queue.task_done()
                
            except queue.Empty:
                # Очередь пуста, ждем
                pass
            except Exception as e:
                print(f"Ошибка при обработке сегмента: {e}")
    
    def get_next_segment(self, timeout=0.5):
        """
        Получает следующий сегмент из очереди
        
        Args:
            timeout (float): Таймаут ожидания в секундах
            
        Returns:
            list or None: Список фреймов или None, если таймаут истек
        """
        try:
            return self.segment_queue.get(timeout=timeout)
        except queue.Empty:
            return None

# Тестовый код (выполняется только при запуске файла напрямую)
if __name__ == "__main__":
    import wave
    import os
    
    # Функция для сохранения сегмента в файл
    def save_segment(segment, filename):
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-бит
            wf.setframerate(16000)
            wf.writeframes(b''.join(segment))
        print(f"Сегмент сохранен в {filename}")
    
    # Функция обратного вызова для обработки сегментов
    def on_segment(segment):
        global segment_count
        filename = f"segment_{segment_count}.wav"
        save_segment(segment, filename)
        segment_count += 1
    
    # Инициализируем процессор
    processor = RealTimeAudioProcessor()
    
    # Получаем список устройств
    print("Доступные устройства ввода:")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"{i}: {device['name']}")
    
    try:
        device_id = int(input("Выберите номер устройства: "))
        
        # Создаем директорию для сегментов
        if not os.path.exists("segments"):
            os.makedirs("segments")
        
        # Счетчик сегментов
        segment_count = 0
        
        # Запускаем обработку
        if processor.start_processing(device_index=device_id, on_segment_ready=on_segment):
            print("Запись запущена. Нажмите Ctrl+C для остановки.")
            
            # Ожидаем обработки в течение 30 секунд или до прерывания
            timeout = 30
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                time.sleep(0.1)
                
            # Останавливаем обработку
            processor.stop_processing()
            print(f"Обработано {segment_count} сегментов.")
        
    except ValueError:
        print("Некорректный номер устройства.")
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        processor.stop_processing()
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        # Гарантируем остановку обработки
        if hasattr(processor, 'is_processing') and processor.is_processing:
            processor.stop_processing()