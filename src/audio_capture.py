import sounddevice as sd
import wave
import threading
import time
import numpy as np
from queue import Queue
import os
import platform
from utils.config import AUDIO_SETTINGS
from src.system_audio_capture import SystemAudioCapture
from src.audio_synchronizer import AudioSynchronizer, EnhancedAudioProcessor

# Windows-specific imports
if platform.system() == 'Windows':
    try:
        from src.windows_audio_capture import WindowsAudioCapture
        WINDOWS_AUDIO_AVAILABLE = True
    except ImportError as e:
        print(f"Windows audio capture not available: {e}")
        WINDOWS_AUDIO_AVAILABLE = False
else:
    WINDOWS_AUDIO_AVAILABLE = False

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
        self.streams = []
        self.current_frames = []
        self.mic_frames = []
        self.output_frames = []
        self.silent_chunks = 0
        self.speaking = False
        
        # Windows-specific audio capture
        self.windows_capture = None
        if WINDOWS_AUDIO_AVAILABLE:
            try:
                self.windows_capture = WindowsAudioCapture(
                    sample_rate=self.rate,
                    channels=self.channels,
                    chunk_size=self.chunk_size
                )
                print("Windows native audio capture available")
            except Exception as e:
                print(f"Failed to initialize Windows audio capture: {e}")
                self.windows_capture = None
        
        # Инициализируем синхронизатор и процессор
        self.audio_sync = AudioSynchronizer(
            sample_rate=self.rate,
            channels=self.channels
        )
        self.audio_processor = EnhancedAudioProcessor(sample_rate=self.rate)
        self.use_synchronizer = False
        
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

    def start_dual_recording(self, input_device_index=None, output_device_index=None):
        """
        Начинает запись аудио одновременно с микрофона и программно с устройства вывода
        
        Args:
            input_device_index: Индекс устройства ввода (микрофон)
            output_device_index: Индекс устройства вывода (наушники/колонки)
        """
        if self.is_recording:
            print("Запись уже идет")
            return
            
        self.is_recording = True
        self.current_frames = []
        self.mic_frames = []
        self.output_frames = []
        self.silent_chunks = 0
        self.speaking = False
        
        # Для хранения потоков
        self.streams = []
        
        try:
            # 1. Создаем поток для записи с микрофона
            mic_stream = sd.InputStream(
                samplerate=self.rate,
                channels=self.channels,
                device=input_device_index,
                blocksize=self.chunk_size,
                dtype='float32',
                callback=self.mic_callback
            )
            
            # Добавляем микрофонный поток
            self.streams.append(mic_stream)
            mic_stream.start()
            print(f"Запись с микрофона (индекс {input_device_index}) началась")
            
            # 2. Ищем Stereo Mix или аналог для захвата звука с устройств вывода
            stereo_mix_idx = None
            devices = sd.query_devices()
            
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    name = device['name'].lower()
                    if "stereo mix" in name or "стереомикшер" in name or "what u hear" in name:
                        stereo_mix_idx = i
                        break
            
            if stereo_mix_idx is not None:
                # Создаем поток для Stereo Mix
                output_stream = sd.InputStream(
                    samplerate=self.rate,
                    channels=self.channels,
                    device=stereo_mix_idx,
                    blocksize=self.chunk_size,
                    dtype='float32',
                    callback=self.output_callback
                )
                
                self.streams.append(output_stream)
                output_stream.start()
                print(f"Запись с системного звука через Stereo Mix (индекс {stereo_mix_idx}) началась")
                print("Звук с микрофона и системы будет смешан")
            else:
                # 3. Если Stereo Mix не найден, пробуем прямую запись с устройства вывода
                try:
                    # На разных платформах параметры могут отличаться
                    output_params = {}
                    
                    # Проверка ОС
                    import platform
                    system = platform.system()
                    
                    if system == "Windows":
                        # На Windows пробуем использовать параметр для loopback
                        # Разные версии sounddevice могут иметь разные параметры
                        
                        # Проверим версию sounddevice
                        sd_version = tuple(map(int, sd.__version__.split('.')[:2]))
                        
                        if sd_version >= (0, 4):
                            # Для новых версий (от 0.4.x) используем extra_settings
                            output_params = {
                                'extra_settings': {
                                    'loopback': True
                                }
                            }
                        else:
                            # Для старых версий может работать прямой параметр wasapi
                            output_params = {
                                'wasapi': True,
                                'loopback': True
                            }
                    
                    # Создаем поток для устройства вывода с дополнительными параметрами
                    # Пробуем несколько подходов для включения loopback режима
                    loopback_methods = [
                        # Метод 1: современный подход с extra_settings
                        {'extra_settings': {'loopback': True}},
                        # Метод 2: прямые параметры (старые версии)
                        {'wasapi': True, 'loopback': True},
                        # Метод 3: только loopback (встречается в некоторых версиях)
                        {'loopback': True}
                    ]
                    
                    loopback_success = False
                    last_error = None
                    
                    # Пробуем разные методы
                    for method_params in loopback_methods:
                        try:
                            print(f"Попытка использования loopback с параметрами: {method_params}")
                            output_stream = sd.InputStream(
                                samplerate=self.rate,
                                channels=self.channels,
                                device=output_device_index,
                                blocksize=self.chunk_size,
                                dtype='float32',
                                callback=self.output_callback,
                                **method_params
                            )
                            
                            self.streams.append(output_stream)
                            output_stream.start()
                            print(f"Запись с устройства вывода (индекс {output_device_index}) началась в режиме loopback")
                            print("Звук с микрофона и устройства вывода будет смешан")
                            loopback_success = True
                            break  # Успешно нашли работающий метод
                        except Exception as e:
                            last_error = e
                            print(f"Метод не сработал: {e}")
                    
                    if not loopback_success:
                        print(f"Все методы записи в режиме loopback не сработали. Последняя ошибка: {last_error}")
                        print("Запись будет производиться только с микрофона")
                        print("Для записи системного звука рекомендуется включить Stereo Mix в настройках Windows")
                        
                except Exception as e:
                    print(f"Ошибка при попытке настройки записи с устройства вывода: {e}")
                    print("Запись будет производиться только с микрофона")
            
        except Exception as e:
            self.is_recording = False
            
            # Закрываем открытые потоки
            for stream in self.streams:
                try:
                    stream.stop()
                    stream.close()
                except:
                    pass
            
            self.streams = []
            print(f"Ошибка при запуске записи: {e}")
            raise
    
    def mic_callback(self, indata, frames, time, status):
        """
        Callback для микрофона
        
        Args:
            indata: Входящие аудиоданные
            frames: Количество фреймов
            time: Информация о времени
            status: Статус аудиопотока
        """
        if status:
            print(f"Статус микрофона: {status}")
            
        # Конвертируем в формат int16
        audio_data = (indata * 32767).astype(np.int16)
        
        # Сохраняем данные микрофона
        self.mic_frames.append(audio_data.copy())
        
        # Обрабатываем данные микрофона
        self._process_audio_data(audio_data)
    
    def output_callback(self, indata, frames, time, status):
        """
        Callback для устройства вывода (системный звук)
        
        Args:
            indata: Входящие аудиоданные
            frames: Количество фреймов
            time: Информация о времени
            status: Статус аудиопотока
        """
        if status:
            print(f"Статус системного звука: {status}")
            
        # Конвертируем в формат int16
        audio_data = (indata * 32767).astype(np.int16)
        
        # Сохраняем данные системного звука
        self.output_frames.append(audio_data.copy())
        
        # Также проверяем данные системного звука на наличие речи
        # (но с повышенным порогом, чтобы не реагировать на фоновые звуки)
        # Получаем байтовое представление
        data = audio_data.tobytes()
        
        # Для системного звука повышаем порог, чтобы не реагировать на тихие звуки
        higher_threshold = self.silence_threshold * 1.5
        
        # Проверяем уровень звука
        volume = np.abs(audio_data).mean()
        
        if volume > higher_threshold and not self.speaking:
            # Если обнаружена активность в системном звуке и еще нет записи,
            # начинаем запись как если бы это была речь
            self.silent_chunks = 0
            self.speaking = True
            print("Обнаружен значимый звук в системном аудио")
            # Добавляем текущий фрейм
            self.current_frames.append(data)
    
    def _process_audio_data(self, audio_data):
        """
        Обрабатывает аудио данные - обнаружение речи и добавление в очередь
        
        Args:
            audio_data: Аудиоданные для обработки
        """
        # Получаем байтовое представление
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
                    # Добавляем сегмент в очередь
                    self.frames_queue.put(self.current_frames.copy())
                    print(f"Фрагмент речи добавлен в очередь (длина: {len(self.current_frames)} чанков)")
                    self.current_frames = []
            
            # Если все еще говорят, продолжаем записывать тишину (для контекста)
            elif self.speaking:
                self.current_frames.append(data)

    def stop_recording(self):
        """
        Останавливает запись аудио
        """
        if not self.is_recording:
            return
            
        self.is_recording = False
        
        # Останавливаем синхронизатор
        if self.use_synchronizer and self.audio_sync:
            self.audio_sync.stop()
            self.use_synchronizer = False
        
        # Останавливаем Windows loopback если он активен
        if self.windows_capture:
            try:
                self.windows_capture.stop_loopback_recording()
            except Exception as e:
                print(f"Ошибка при остановке Windows loopback: {e}")
        
        # Останавливаем все потоки записи
        if hasattr(self, 'streams') and self.streams:
            for stream in self.streams:
                if stream:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception as e:
                        print(f"Ошибка при остановке потока: {e}")
            self.streams = []
        
        # Для обратной совместимости
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                print(f"Ошибка при остановке основного потока: {e}")
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
        # Если синхронизатор активен, получаем данные оттуда
        if self.use_synchronizer and self.audio_sync:
            # Получаем синхронизированное аудио
            sync_audio = self.audio_sync.get_synchronized_audio(timeout=0.1)
            
            if sync_audio is not None:
                # Применяем улучшение качества
                processed_audio = self.audio_processor.process(sync_audio)
                
                # Конвертируем в int16 и возвращаем как список байтов
                int_audio = (processed_audio * 32767).astype(np.int16)
                return [int_audio.tobytes()]
        
        # Стандартный метод
        if not self.frames_queue.empty():
            return self.frames_queue.get()
        return None
    
    def start_enhanced_recording(self, input_device_index=None, output_device_index=None):
        """
        Начинает улучшенную запись аудио с использованием нативных Windows API
        когда это возможно, с откатом на универсальный метод
        
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
        self.streams = []
        
        # Включаем синхронизатор
        self.use_synchronizer = True
        self.audio_sync.reset_buffers()
        self.audio_sync.start()
        
        try:
            # 1. Запускаем запись с микрофона
            mic_stream = sd.InputStream(
                samplerate=self.rate,
                channels=self.channels,
                device=input_device_index,
                blocksize=self.chunk_size,
                dtype='float32',
                callback=self._enhanced_mic_callback  # Используем улучшенный callback
            )
            
            self.streams.append(mic_stream)
            mic_stream.start()
            print(f"Запись с микрофона (индекс {input_device_index}) началась")
            
            # 2. Пробуем использовать Windows native loopback если доступно
            loopback_started = False
            if self.windows_capture and platform.system() == 'Windows':
                try:
                    print("Попытка использования Windows native loopback...")
                    self.windows_capture.start_loopback_recording()
                    loopback_started = True
                    
                    # Запускаем поток для обработки loopback аудио
                    threading.Thread(
                        target=self._process_windows_loopback,
                        daemon=True
                    ).start()
                    
                    print("Windows native loopback запущен успешно")
                except Exception as e:
                    print(f"Не удалось запустить Windows loopback: {e}")
                    loopback_started = False
            
            # 3. Если Windows loopback не удался, пробуем альтернативные методы
            if not loopback_started:
                # Используем универсальный метод захвата
                self.system_capture = SystemAudioCapture(
                    sample_rate=self.rate,
                    channels=self.channels,
                    chunk_size=self.chunk_size
                )
                
                threading.Thread(
                    target=self._capture_system_audio,
                    args=(output_device_index,),
                    daemon=True
                ).start()
                
                print("Используется альтернативный метод захвата системного звука")
            
            print("Улучшенная запись звука запущена")
            
            # Запускаем поток для обработки синхронизированного аудио
            threading.Thread(
                target=self._process_synchronized_audio,
                daemon=True
            ).start()
            
        except Exception as e:
            self.is_recording = False
            
            # Закрываем открытые потоки
            for stream in self.streams:
                try:
                    stream.stop()
                    stream.close()
                except:
                    pass
            
            self.streams = []
            print(f"Ошибка при запуске записи: {e}")
            raise
    
    def _enhanced_mic_callback(self, indata, frames, time, status):
        """
        Callback для микрофона в улучшенном режиме
        
        Args:
            indata: Входящие аудиоданные
            frames: Количество фреймов
            time: Информация о времени
            status: Статус аудиопотока
        """
        if status:
            print(f"Статус микрофона: {status}")
        
        # Конвертируем в float32 для синхронизатора
        audio_data = indata.copy()
        
        # Если синхронизатор активен, отправляем данные туда
        if self.use_synchronizer:
            self.audio_sync.add_mic_data(audio_data)
        
        # Также обрабатываем стандартным способом для детекции речи
        self._process_audio_data((audio_data * 32767).astype(np.int16))
    
    def _process_windows_loopback(self):
        """
        Обрабатывает аудио данные от Windows loopback
        """
        print("Запущен поток обработки Windows loopback")
        
        while self.is_recording and self.windows_capture:
            try:
                # Получаем данные от loopback
                audio_data = self.windows_capture.get_loopback_audio()
                
                if audio_data is not None and len(audio_data) > 0:
                    # Если синхронизатор активен, отправляем данные туда
                    if self.use_synchronizer:
                        self.audio_sync.add_system_data(audio_data)
                    else:
                        # Обрабатываем данные обычным способом
                        self._process_system_audio(audio_data)
                
                # Небольшая пауза
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Ошибка при обработке Windows loopback: {e}")
                break
        
        print("Поток обработки Windows loopback завершен")
    
    def _process_synchronized_audio(self):
        """
        Обрабатывает синхронизированное аудио и добавляет в очередь
        """
        print("Запущен поток обработки синхронизированного аудио")
        
        while self.is_recording and self.use_synchronizer:
            try:
                # Получаем синхронизированное аудио
                sync_audio = self.audio_sync.get_synchronized_audio(timeout=0.5)
                
                if sync_audio is not None and len(sync_audio) > 0:
                    # Применяем улучшение качества
                    processed_audio = self.audio_processor.process(sync_audio)
                    
                    # Конвертируем в int16
                    int_audio = (processed_audio * 32767).astype(np.int16)
                    
                    # Проверяем на тишину и речь
                    volume = np.abs(int_audio).mean()
                    
                    if volume > self.silence_threshold:
                        self.silent_chunks = 0
                        
                        if not self.speaking:
                            self.speaking = True
                            print("Речь обнаружена (синхронизированное аудио)")
                        
                        self.current_frames.append(int_audio.tobytes())
                    else:
                        self.silent_chunks += 1
                        
                        if self.speaking and self.silent_chunks > int(self.rate / self.chunk_size * self.silence_duration):
                            self.speaking = False
                            
                            if self.current_frames:
                                self.frames_queue.put(self.current_frames.copy())
                                print(f"Фрагмент речи добавлен в очередь (синхронизированный)")
                                self.current_frames = []
                        
                        elif self.speaking:
                            self.current_frames.append(int_audio.tobytes())
                            
            except Exception as e:
                print(f"Ошибка при обработке синхронизированного аудио: {e}")
                
            time.sleep(0.01)
        
        print("Поток обработки синхронизированного аудио завершен")
    
    def _process_synchronized_audio(self):
        """
        Обрабатывает синхронизированное аудио и добавляет в очередь
        """
        print("Запущен поток обработки синхронизированного аудио")
        
        while self.is_recording and self.use_synchronizer:
            try:
                # Получаем синхронизированное аудио
                sync_audio = self.audio_sync.get_synchronized_audio(timeout=0.5)
                
                if sync_audio is not None and len(sync_audio) > 0:
                    # Применяем улучшение качества
                    processed_audio = self.audio_processor.process(sync_audio)
                    
                    # Конвертируем в int16
                    int_audio = (processed_audio * 32767).astype(np.int16)
                    
                    # Проверяем на тишину и речь
                    volume = np.abs(int_audio).mean()
                    
                    if volume > self.silence_threshold:
                        self.silent_chunks = 0
                        
                        if not self.speaking:
                            self.speaking = True
                            print("Речь обнаружена (синхронизированное аудио)")
                        
                        self.current_frames.append(int_audio.tobytes())
                    else:
                        self.silent_chunks += 1
                        
                        if self.speaking and self.silent_chunks > int(self.rate / self.chunk_size * self.silence_duration):
                            self.speaking = False
                            
                            if self.current_frames:
                                self.frames_queue.put(self.current_frames.copy())
                                print(f"Фрагмент речи добавлен в очередь (синхронизированный)")
                                self.current_frames = []
                        
                        elif self.speaking:
                            self.current_frames.append(int_audio.tobytes())
                            
            except Exception as e:
                print(f"Ошибка при обработке синхронизированного аудио: {e}")
                
            time.sleep(0.01)
        
        print("Поток обработки синхронизированного аудио завершен")
    
    def start_universal_recording(self, input_device_index=None, output_device_index=None):
        """
        Начинает запись аудио с микрофона и системного звука с использованием
        универсального метода, который автоматически выбирает оптимальный способ
        захвата звука для текущей системы
        
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
        
        # Для хранения потоков
        self.streams = []
        
        try:
            # 1. Создаем поток для записи с микрофона
            mic_stream = sd.InputStream(
                samplerate=self.rate,
                channels=self.channels,
                device=input_device_index,
                blocksize=self.chunk_size,
                dtype='float32',
                callback=self.audio_callback
            )
            
            self.streams.append(mic_stream)
            mic_stream.start()
            print(f"Запись с микрофона (индекс {input_device_index}) началась")
            
            # 2. Создаем объект для захвата системного звука
            self.system_capture = SystemAudioCapture(
                sample_rate=self.rate,
                channels=self.channels,
                chunk_size=self.chunk_size
            )
            
            # Запускаем захват системного звука в отдельном потоке
            threading.Thread(
                target=self._capture_system_audio,
                args=(output_device_index,),
                daemon=True
            ).start()
            
            print("Захват системного звука запущен")
            print("Звук с микрофона и системы будет объединен")
            
        except Exception as e:
            self.is_recording = False
            
            # Закрываем открытые потоки
            for stream in self.streams:
                try:
                    stream.stop()
                    stream.close()
                except:
                    pass
            
            self.streams = []
            print(f"Ошибка при запуске записи: {e}")
            raise
    
    def _capture_system_audio(self, device_index):
        """
        Функция для захвата системного звука в отдельном потоке
        
        Args:
            device_index: Индекс устройства вывода
        """
        try:
            # Запускаем захват системного звука
            self.system_capture.start_recording(device_index)
            
            # Регулярно получаем данные и обрабатываем их
            while self.is_recording:
                # Подождем немного, чтобы накопились данные
                time.sleep(0.5)
                
                # Получаем данные
                audio_data = self.system_capture.get_audio_data()
                
                if audio_data is not None:
                    # Обрабатываем данные так же, как и с микрофона
                    self._process_system_audio(audio_data)
            
            # Останавливаем захват
            self.system_capture.stop_recording()
            
        except Exception as e:
            print(f"Ошибка при захвате системного звука: {e}")
    
    def _process_system_audio(self, audio_data):
        """
        Обрабатывает аудиоданные от системного звука
        
        Args:
            audio_data: Аудиоданные в формате numpy array
        """
        # Конвертируем в формат int16
        int_data = (audio_data * 32767).astype(np.int16)
        
        # Получаем байтовое представление
        data = int_data.tobytes()
        
        # Проверка на тишину
        volume = np.abs(int_data).mean()
        
        # Для системного звука повышаем порог, чтобы не реагировать на тихие звуки
        higher_threshold = self.silence_threshold * 1.5
        
        if volume > higher_threshold:
            self.silent_chunks = 0
            
            if not self.speaking:
                self.speaking = True
                print("Обнаружен значимый звук в системном аудио")
            
            self.current_frames.append(data)
        else:
            # Тишина обрабатывается в основном коллбэке микрофона
            pass


    def close(self):
        """
        Закрывает ресурсы записи
        """
        self.stop_recording()
        
        # Останавливаем Windows loopback
        if self.windows_capture:
            try:
                self.windows_capture.stop_loopback_recording()
            except Exception as e:
                print(f"Ошибка при остановке Windows loopback: {e}")
        
        # Если есть объект захвата системного звука, также останавливаем его
        if hasattr(self, 'system_capture'):
            try:
                self.system_capture.stop_recording()
            except Exception as e:
                print(f"Ошибка при остановке захвата системного звука: {e}")
                pass


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
        # Спрашиваем, какой режим использовать
        print("\nВыберите режим записи:")
        print("1. Стандартная запись с микрофона и системного звука (через Stereo Mix, если доступно)")
        print("2. Продвинутая запись с прямым захватом звука с устройства вывода (может потребоваться дополнительная настройка)")
        
        mode_choice = int(input("Введите номер режима: "))
        
        if mode_choice == 1:
            print(f"Начинаем запись с микрофона {input_device_name} и вывода звука (стандартный режим)...")
            audio_capture.start_recording_with_both(
                input_device_index=input_device_id, 
                output_device_index=output_device_id
            )
        else:
            print(f"Начинаем запись с микрофона {input_device_name} и вывода звука (продвинутый режим)...")
            audio_capture.start_dual_recording(
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