import sounddevice as sd
import threading
import time
import numpy as np
from queue import Queue
from datetime import datetime
from utils.config import AUDIO_SETTINGS
from src.system_audio_capture import SystemAudioCapture
from src.audio_synchronizer import AudioSynchronizer, EnhancedAudioProcessor
from src.vad import create_vad

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
        # 0.7 сек тишины достаточно для сегментации диалога (было 2.0 — слишком много)
        self.silence_duration = AUDIO_SETTINGS.get('silence_duration_vad', 0.7)
        # Максимальная длина сегмента: 15 сек (Whisper плохо работает с >30 сек)
        self.max_segment_duration = AUDIO_SETTINGS.get('max_segment_duration', 15.0)
        self.stream = None
        self.streams = []
        self.current_frames = []
        self.silent_chunks = 0
        self.speaking = False
        # Время начала текущего сегмента речи
        self._segment_start_time: datetime | None = None

        # VAD: Silero если доступен, иначе RMS
        self._vad = create_vad(threshold=0.5, rms_threshold=silence_threshold, sample_rate=rate)
        print(f"VAD инициализирован: {type(self._vad).__name__}")
        
        # Инициализируем синхронизатор и процессор
        self.audio_sync = AudioSynchronizer(
            sample_rate=self.rate,
            channels=self.channels
        )
        self.audio_processor = EnhancedAudioProcessor(sample_rate=self.rate)
        self.use_synchronizer = False
        
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
    
    def _process_audio_data(self, audio_data, speaker: str = "local"):
        """
        Обрабатывает аудиоданные — детекция речи через VAD и добавление в очередь.

        Args:
            audio_data: int16 numpy array
            speaker: "local" (микрофон) или "remote" (системный звук)
        """
        data = audio_data.tobytes()

        # Конвертируем в float32 для VAD
        audio_f32 = audio_data.astype(np.float32) / 32767.0
        is_speech = self._vad.is_speech(audio_f32)

        if is_speech:
            self.silent_chunks = 0
            if not self.speaking:
                self.speaking = True
                self._segment_start_time = datetime.now()
            self.current_frames.append(data)

            max_chunks = int(self.rate / self.chunk_size * self.max_segment_duration)
            if len(self.current_frames) >= max_chunks:
                self._flush_segment(speaker=speaker)
        else:
            self.silent_chunks += 1
            silence_chunks_threshold = int(self.rate / self.chunk_size * self.silence_duration)

            if self.speaking and self.silent_chunks > silence_chunks_threshold:
                self._flush_segment(speaker=speaker)
            elif self.speaking:
                self.current_frames.append(data)

    def _flush_segment(self, speaker: str = "local"):
        """
        Отправляет накопленный сегмент в очередь с метаданными.

        Формат элемента очереди:
            {
                "frames": list[bytes],
                "speaker": "local" | "remote",
                "start_time": datetime,
                "end_time": datetime,
            }
        """
        if not self.current_frames:
            return
        self.frames_queue.put({
            "frames": self.current_frames.copy(),
            "speaker": speaker,
            "start_time": self._segment_start_time or datetime.now(),
            "end_time": datetime.now(),
        })
        print(f"Сегмент в очереди: speaker={speaker}, чанков={len(self.current_frames)}")
        self.current_frames = []
        self.speaking = False
        self._segment_start_time = None

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
    
    def get_next_audio_segment(self):
        """
        Получает следующий сегмент аудио из очереди, если доступен.

        Returns:
            dict с полями:
                "frames"    : list[bytes] — аудиоданные
                "speaker"   : "local" | "remote" — источник
                "start_time": datetime — начало сегмента
                "end_time"  : datetime — конец сегмента
            или None если очередь пуста.
        """
        # Если синхронизатор активен, получаем данные оттуда
        if self.use_synchronizer and self.audio_sync:
            sync_audio = self.audio_sync.get_synchronized_audio(timeout=0.1)
            if sync_audio is not None:
                processed_audio = self.audio_processor.process(sync_audio)
                int_audio = (processed_audio * 32767).astype(np.int16)
                return {
                    "frames": [int_audio.tobytes()],
                    "speaker": "local",
                    "start_time": datetime.now(),
                    "end_time": datetime.now(),
                }

        if not self.frames_queue.empty():
            segment = self.frames_queue.get()
            # Backward-compat: если в очереди старый формат (list), оборачиваем
            if isinstance(segment, list):
                return {
                    "frames": segment,
                    "speaker": "local",
                    "start_time": datetime.now(),
                    "end_time": datetime.now(),
                }
            return segment
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
            
            # 2. Захват системного звука через SystemAudioCapture
            if True:
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
                    int_data = (audio_data * 32767).astype(np.int16)
                    self._process_audio_data(int_data, speaker="remote")
            
            # Останавливаем захват
            self.system_capture.stop_recording()
            
        except Exception as e:
            print(f"Ошибка при захвате системного звука: {e}")
    
    def close(self):
        """
        Закрывает ресурсы записи
        """
        self.stop_recording()

        # Если есть объект захвата системного звука, также останавливаем его
        if hasattr(self, 'system_capture'):
            try:
                self.system_capture.stop_recording()
            except Exception as e:
                print(f"Ошибка при остановке захвата системного звука: {e}")
                pass
