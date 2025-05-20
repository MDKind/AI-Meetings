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
        Выводит список доступных аудио устройств (ввода и вывода)
        
        Returns:
            list: Список кортежей (индекс, название, тип) устройств
        """
        devices = sd.query_devices()
        audio_devices = []
        
        print("\n=== УСТРОЙСТВА ВВОДА (МИКРОФОНЫ) ===")
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                name = device['name']
                # Проверяем, является ли это виртуальным микрофоном или стереомикшером
                if "stereo mix" in name.lower() or "стереомикшер" in name.lower() or "what u hear" in name.lower():
                    device_type = "system_sound"
                    audio_devices.append((i, f"{name} (Системный звук)", device_type))
                    print(f"Device {i}: {name} (Системный звук)")
                else:
                    device_type = "microphone"
                    audio_devices.append((i, f"{name} (Микрофон)", device_type))
                    print(f"Device {i}: {name} (Микрофон)")
                print(f"  Input channels: {device['max_input_channels']}")
                print(f"  Default sample rate: {device['default_samplerate']}")
                print()
        
        print("\n=== УСТРОЙСТВА ВЫВОДА (ДИНАМИКИ, НАУШНИКИ) ===")
        for i, device in enumerate(devices):
            if device['max_output_channels'] > 0:
                name = device['name']
                device_type = "output"
                audio_devices.append((i, f"{name} (Вывод)", device_type))
                print(f"Device {i}: {name} (Вывод)")
                print(f"  Output channels: {device['max_output_channels']}")
                print(f"  Default sample rate: {device['default_samplerate']}")
                print()
        
        return audio_devices
        
    def list_input_devices(self):
        """
        Выводит список доступных аудио устройств ввода (микрофоны)
        
        Returns:
            list: Список кортежей (индекс, название, тип) устройств ввода
        """
        devices = sd.query_devices()
        input_devices = []
        
        print("\n=== УСТРОЙСТВА ВВОДА (МИКРОФОНЫ) ===")
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                name = device['name']
                # Проверяем, является ли это виртуальным микрофоном или стереомикшером
                if "stereo mix" in name.lower() or "стереомикшер" in name.lower() or "what u hear" in name.lower():
                    device_type = "system_sound"
                    input_devices.append((i, f"{name} (Системный звук)", device_type))
                    print(f"Device {i}: {name} (Системный звук)")
                else:
                    device_type = "microphone"
                    input_devices.append((i, f"{name} (Микрофон)", device_type))
                    print(f"Device {i}: {name} (Микрофон)")
                print(f"  Input channels: {device['max_input_channels']}")
                print(f"  Default sample rate: {device['default_samplerate']}")
                print()
        
        return input_devices

    def list_output_devices(self):
        """
        Выводит список доступных аудио устройств вывода (динамики, наушники)
        
        Returns:
            list: Список кортежей (индекс, название, тип) устройств вывода
        """
        devices = sd.query_devices()
        output_devices = []
        
        print("\n=== УСТРОЙСТВА ВЫВОДА (ДИНАМИКИ, НАУШНИКИ) ===")
        for i, device in enumerate(devices):
            if device['max_output_channels'] > 0:
                name = device['name']
                device_type = "output"
                output_devices.append((i, f"{name} (Вывод)", device_type))
                print(f"Device {i}: {name} (Вывод)")
                print(f"  Output channels: {device['max_output_channels']}")
                print(f"  Default sample rate: {device['default_samplerate']}")
                print()
        
        return output_devices
    
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
    
    def start_recording(self, device_index=None, device_type=None):
        """
        Начинает запись аудио с выбранного устройства
        
        Args:
            device_index: Индекс устройства
            device_type: Тип устройства ("microphone", "system_sound", "output")
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
            if device_type == "output":
                # Для устройств вывода найдем устройство Stereo Mix или аналог
                devices = sd.query_devices()
                stereo_mix_idx = None
                
                for i, device in enumerate(devices):
                    if device['max_input_channels'] > 0:
                        name = device['name'].lower()
                        if "stereo mix" in name or "стереомикшер" in name or "what u hear" in name:
                            stereo_mix_idx = i
                            break
                
                if stereo_mix_idx is not None:
                    print(f"Найдено устройство для захвата звука системы: {devices[stereo_mix_idx]['name']}")
                    self.stream = sd.InputStream(
                        samplerate=self.rate,
                        channels=self.channels,
                        device=stereo_mix_idx,
                        blocksize=self.chunk_size,
                        dtype='float32',
                        callback=self.audio_callback
                    )
                    self.stream.start()
                    print(f"Запись с системного аудио через {devices[stereo_mix_idx]['name']} (индекс {stereo_mix_idx})...")
                else:
                    # Если Stereo Mix не найден, сообщаем о необходимости его включения
                    raise Exception(
                        "Не удалось найти устройство для захвата системного звука (Stereo Mix или аналоги). "
                        "Для записи с устройств вывода необходимо включить 'Стереомикшер' в панели управления звуком "
                        "или установить виртуальное аудиоустройство типа VB-Cable."
                    )
            else:
                # Обычный режим записи для устройств ввода (микрофонов и системного звука)
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
    
    def start_recording_with_both(self, input_device_index=None, output_device_index=None):
        """
        Начинает запись аудио с микрофона и одновременно с выходного устройства через Stereo Mix.
        
        Args:
            input_device_index: Индекс устройства ввода (микрофон)
            output_device_index: Индекс устройства вывода (наушники/колонки)
        """
        if self.is_recording:
            print("Запись уже идет")
            return
            
        self.is_recording = True
        self.current_frames = []
        self.silent_chunks = 0
        self.speaking = False
        
        # Ищем Stereo Mix для захвата звука с устройств вывода
        stereo_mix_idx = None
        devices = sd.query_devices()
        
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                name = device['name'].lower()
                if "stereo mix" in name or "стереомикшер" in name or "what u hear" in name:
                    stereo_mix_idx = i
                    break
        
        # Запускаем поток записи с выбранного микрофона
        try:
            self.stream = sd.InputStream(
                samplerate=self.rate,
                channels=self.channels,
                device=input_device_index,
                blocksize=self.chunk_size,
                dtype='float32',
                callback=self.audio_callback
            )
            
            self.stream.start()
            
            # Если нашли Stereo Mix, информируем что он будет использоваться для записи звука системы
            if stereo_mix_idx is not None:
                print(f"Запись с микрофона (индекс {input_device_index}) включена.")
                print(f"Для записи звука с наушников ({output_device_index}) будет использовано устройство {devices[stereo_mix_idx]['name']} (индекс {stereo_mix_idx}).")
                print("Примечание: звук системы будет захвачен через Stereo Mix, независимо от выбранного выходного устройства.")
            else:
                # Если Stereo Mix не найден, информируем что запись с выходного устройства недоступна
                print(f"Запись с микрофона (индекс {input_device_index}) включена.")
                print("Запись с выходного устройства недоступна, так как не найден Stereo Mix или аналог.")
                print("Для включения записи с выходных устройств активируйте 'Стереомикшер' в панели управления звуком Windows.")
                
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
    input_devices = audio_capture.list_input_devices()
    output_devices = audio_capture.list_output_devices()
    
    if not input_devices:
        print("Не найдено устройств ввода аудио!")
        exit(1)
    
    # Выберите устройство ввода (микрофон)
    print("\nВыберите устройство ввода (микрофон):")
    for i, (device_id, name, device_type) in enumerate(input_devices):
        print(f"{i}: {name} [{device_type}]")
    
    input_choice = int(input("Введите номер устройства ввода: "))
    if 0 <= input_choice < len(input_devices):
        input_device_id, input_device_name, input_device_type = input_devices[input_choice]
        print(f"Выбрано устройство ввода: {input_device_name} [{input_device_type}]")
    else:
        print("Неверный номер устройства ввода.")
        exit(1)
    
    # Выберите устройство вывода (наушники, колонки)
    if output_devices:
        print("\nВыберите устройство вывода (наушники, колонки):")
        for i, (device_id, name, device_type) in enumerate(output_devices):
            print(f"{i}: {name} [{device_type}]")
        
        output_choice = int(input("Введите номер устройства вывода: "))
        if 0 <= output_choice < len(output_devices):
            output_device_id, output_device_name, output_device_type = output_devices[output_choice]
            print(f"Выбрано устройство вывода: {output_device_name} [{output_device_type}]")
        else:
            print("Неверный номер устройства вывода.")
            exit(1)
    else:
        print("Устройства вывода не найдены.")
        output_device_id = None
    
    try:
        print(f"Начинаем запись с микрофона {input_device_name} и вывода звука...")
        audio_capture.start_recording_with_both(
            input_device_index=input_device_id, 
            output_device_index=output_device_id
        )
        
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
    finally:
        audio_capture.close()