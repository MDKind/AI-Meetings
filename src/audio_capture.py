import sounddevice as sd
import wave
import threading
import time
import numpy as np
from queue import Queue
import os
from utils.config import AUDIO_SETTINGS

class AudioCapture:
    """
    Класс для захвата аудио с устройства ввода (микрофона/наушников)
    и системного звука
    """
    def __init__(self, 
                 chunk_size=AUDIO_SETTINGS['chunk_size'], 
                 channels=AUDIO_SETTINGS['channels'], 
                 rate=AUDIO_SETTINGS['rate'],
                 silence_threshold=AUDIO_SETTINGS['silence_threshold']):
        """
        Инициализация объекта захвата аудио
        
        Args:
            chunk_size (int): Размер чанка аудио для обработки
            channels (int): Количество каналов (1 для моно, 2 для стерео)
            rate (int): Частота дискретизации (Гц)
            silence_threshold (int): Порог тишины для детектирования речи
        """
        self.chunk_size = chunk_size
        self.channels = channels
        self.rate = rate
        self.frames_queue = Queue()
        self.is_recording = False
        self.silence_threshold = silence_threshold
        self.silence_duration = AUDIO_SETTINGS['silence_duration']
        self.stream = None
        self.current_frames = []
        self.silent_chunks = 0
        self.speaking = False
        
    def list_devices(self):
        """
        Выводит список доступных аудио устройств
        
        Returns:
            list: Список кортежей (индекс, название) устройств ввода
        """
        devices = sd.query_devices()
        audio_devices = []
        
        print("\n=== УСТРОЙСТВА ВВОДА (МИКРОФОНЫ) ===")
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                name = device['name']
                # Проверяем, является ли это виртуальным микрофоном или стереомикшером
                if "stereo mix" in name.lower() or "стереомикшер" in name.lower() or "what u hear" in name.lower():
                    audio_devices.append((i, f"{name} (Системный звук)"))
                    print(f"Device {i}: {name} (Системный звук)")
                else:
                    audio_devices.append((i, f"{name} (Микрофон)"))
                    print(f"Device {i}: {name} (Микрофон)")
                print(f"  Input channels: {device['max_input_channels']}")
                print(f"  Default sample rate: {device['default_samplerate']}")
                print()
        
        return audio_devices
    
    def audio_callback(self, indata, frames, time, status):
        """
        Callback функция для обработки входящих аудиоданных
        
        Args:
            indata: Входящие аудиоданные
            frames: Количество фреймов
            time: Информация о времени
            status: Статус аудиопотока
        """
        if status:
            print(f"Статус: {status}")
            
        # Конвертируем в формат int16 для совместимости
        audio_data = (indata * 32767).astype(np.int16)
        
        # Получаем байтовое представление для совместимости с wave
        data = audio_data.tobytes()
        
        # Проверка на тишину
        volume = np.abs(audio_data).mean()
        
        if volume > self.silence_threshold:
            self.silent_chunks = 0
            
            if not self.speaking:
                self.speaking = True
                print("Речь обнаружена")
            
            self.current_frames.append(data)
        else:
            self.silent_chunks += 1
            
            # Если речь закончилась и есть что обрабатывать
            if self.speaking and self.silent_chunks > int(self.rate / self.chunk_size * self.silence_duration):
                self.speaking = False
                
                if self.current_frames:
                    self.frames_queue.put(self.current_frames.copy())
                    print(f"Фрагмент речи добавлен в очередь (длина: {len(self.current_frames)} чанков)")
                    self.current_frames = []
            
            # Если все еще говорят, продолжаем записывать тишину (для контекста)
            elif self.speaking:
                self.current_frames.append(data)
    
    def start_recording(self, device_index=None):
        """
        Начинает запись аудио с выбранного устройства
        
        Args:
            device_index: Индекс устройства ввода
        """
        if self.is_recording:
            print("Запись уже идет")
            return
            
        self.is_recording = True
        self.current_frames = []
        self.silent_chunks = 0
        self.speaking = False
        
        # Запускаем поток записи
        try:
            # Обычный режим записи для всех типов устройств
            self.stream = sd.InputStream(
                samplerate=self.rate,
                channels=self.channels,
                device=device_index,
                blocksize=self.chunk_size,
                dtype='float32',
                callback=self.audio_callback
            )
                
            self.stream.start()
            print(f"Запись с устройства {device_index} началась...")
        except Exception as e:
            self.is_recording = False
            print(f"Ошибка при запуске записи: {e}")
            raise
    
    def stop_recording(self):
        """
        Останавливает запись аудио
        """
        if not self.is_recording:
            return
            
        self.is_recording = False
        
        # Останавливаем поток записи
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            
        print("Запись аудио остановлена.")
    
    def save_audio(self, frames, filename="output.wav"):
        """
        Сохраняет аудио данные в файл WAV
        
        Args:
            frames (list): Список фреймов аудио
            filename (str): Имя файла для сохранения
        """
        wf = wave.open(filename, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(frames))
        wf.close()
        print(f"Аудио сохранено в {filename}")
    
    def get_next_audio_segment(self):
        """
        Получает следующий сегмент аудио из очереди, если доступен
        
        Returns:
            list: Список фреймов аудио или None, если очередь пуста
        """
        if not self.frames_queue.empty():
            return self.frames_queue.get()
        return None
    
    def close(self):
        """
        Закрывает ресурсы записи
        """
        self.stop_recording()


# Тестовый код (выполняется только при запуске файла напрямую)
if __name__ == "__main__":
    # Инициализация захвата аудио
    audio_capture = AudioCapture()
    
    print("Доступные аудио устройства:")
    devices = audio_capture.list_devices()
    
    if not devices:
        print("Не найдено устройств ввода аудио!")
        exit(1)
    
    # Выберите нужное устройство
    print("\nВыберите устройство:")
    for i, (device_id, name) in enumerate(devices):
        print(f"{i}: {name}")
    
    try:
        choice = int(input("Введите номер устройства: "))
        if 0 <= choice < len(devices):
            device_id, device_name = devices[choice]
            print(f"Выбрано устройство: {device_name}")
            
            try:
                print(f"Начинаем запись с устройства {device_name}")
                audio_capture.start_recording(device_index=device_id)
                
                # Запустим 10-секундную запись в качестве теста
                print("Запись будет длиться 10 секунд...")
                time.sleep(10)
                
                # Останавливаем запись
                audio_capture.stop_recording()
                
                # Получаем и сохраняем все сегменты аудио
                segment_idx = 0
                while True:
                    frames = audio_capture.get_next_audio_segment()
                    if frames is None:
                        break
                    
                    audio_capture.save_audio(frames, f"audio_segment_{segment_idx}.wav")
                    segment_idx += 1
                
                if segment_idx == 0:
                    print("Не было обнаружено речи.")
                else:
                    print(f"Сохранено {segment_idx} аудио сегментов.")
            except Exception as e:
                print(f"Ошибка при записи: {e}")
                
        else:
            print("Неверный номер устройства.")
    except ValueError:
        print("Неверный ввод.")
    except KeyboardInterrupt:
        print("Запись прервана пользователем")
    finally:
        audio_capture.close()