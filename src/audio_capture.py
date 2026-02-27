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
        self._mic_raw_queue = Queue()  # сырые чанки с микрофона (float32 int16)
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
        self._vad_lock = threading.Lock()
        print(f"VAD инициализирован: {type(self._vad).__name__}")

        # Отдельный VAD + состояние для системного звука (изолировано от mic-пути)
        self._sys_vad = create_vad(threshold=0.5, rms_threshold=silence_threshold, sample_rate=rate)
        self._sys_frames: list[bytes] = []
        self._sys_speaking = False
        self._sys_silent_chunks = 0
        self._sys_segment_start: datetime | None = None
        
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
        with self._vad_lock:
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
        self._segment_start_time = None
        self.streams = []
        self.use_synchronizer = False  # Синхронизатор не используется

        # Сбрасываем состояние системного аудио
        self._sys_frames = []
        self._sys_speaking = False
        self._sys_silent_chunks = 0
        self._sys_segment_start = None
        if hasattr(self._sys_vad, 'reset'):
            self._sys_vad.reset()
        if hasattr(self._vad, 'reset'):
            self._vad.reset()

        try:
            # 1. Микрофон — напрямую через _process_audio_data (speaker="local")
            mic_stream = sd.InputStream(
                samplerate=self.rate,
                channels=self.channels,
                device=input_device_index,
                blocksize=self.chunk_size,
                dtype='float32',
                callback=self._mic_callback,
            )
            self.streams.append(mic_stream)
            mic_stream.start()
            print(f"Запись с микрофона (индекс {input_device_index}) началась")

            # 2. Системный звук — через SystemAudioCapture в отдельном потоке
            self.system_capture = SystemAudioCapture(
                sample_rate=self.rate,
                channels=self.channels,
                chunk_size=self.chunk_size,
            )
            threading.Thread(
                target=self._capture_system_audio,
                args=(output_device_index,),
                daemon=True,
            ).start()
            print("Захват системного звука запущен")

            # Поток обработки mic (VAD + сегментация вне PortAudio callback)
            threading.Thread(
                target=self._mic_processing_thread,
                daemon=True,
            ).start()

            print("Запись звука запущена")
            
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
    
    def _mic_callback(self, indata, frames, time_info, status):
        """Callback sounddevice для микрофона — только кладёт данные в очередь."""
        if status:
            print(f"Статус микрофона: {status}")
        self._mic_raw_queue.put((indata.copy() * 32767).astype(np.int16))

    def _mic_processing_thread(self):
        """Обрабатывает сырые mic-чанки в отдельном потоке (VAD, сегментация)."""
        while self.is_recording:
            try:
                chunk = self._mic_raw_queue.get(timeout=0.2)
                self._process_audio_data(chunk, speaker="local")
            except Exception:
                pass
    
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

    def _process_system_chunk(self, chunk_i16_1d: np.ndarray):
        """
        Обрабатывает один chunk_size системного звука через изолированный VAD+сегментатор.
        Вызывается только из _capture_system_audio (один поток — нет race).
        """
        data = chunk_i16_1d.tobytes()
        audio_f32 = chunk_i16_1d.astype(np.float32) / 32767.0
        is_speech = self._sys_vad.is_speech(audio_f32)

        max_chunks = int(self.rate / self.chunk_size * self.max_segment_duration)
        silence_chunks_threshold = int(self.rate / self.chunk_size * self.silence_duration)

        if is_speech:
            self._sys_silent_chunks = 0
            if not self._sys_speaking:
                self._sys_speaking = True
                self._sys_segment_start = datetime.now()
            self._sys_frames.append(data)
            if len(self._sys_frames) >= max_chunks:
                self._flush_sys_segment()
        else:
            self._sys_silent_chunks += 1
            if self._sys_speaking and self._sys_silent_chunks > silence_chunks_threshold:
                self._flush_sys_segment()
            elif self._sys_speaking:
                self._sys_frames.append(data)

    def _flush_sys_segment(self):
        if not self._sys_frames:
            return
        self.frames_queue.put({
            "frames": self._sys_frames.copy(),
            "speaker": "remote",
            "start_time": self._sys_segment_start or datetime.now(),
            "end_time": datetime.now(),
        })
        print(f"Сегмент в очереди: speaker=remote, чанков={len(self._sys_frames)}")
        self._sys_frames = []
        self._sys_speaking = False
        self._sys_silent_chunks = 0
        self._sys_segment_start = None

    def _capture_system_audio(self, device_index):
        """
        Функция для захвата системного звука в отдельном потоке.
        Использует изолированный VAD и сегментатор (нет race с mic-потоком).
        """
        try:
            self.system_capture.start_recording(device_index)

            while self.is_recording:
                time.sleep(0.1)

                audio_data = self.system_capture.get_audio_data()
                if audio_data is None:
                    continue

                # audio_data: float32, shape (N,) или (N, 1) — нормализуем
                samples = audio_data.flatten()

                # Конвертируем в int16 для совместимости с остальным пайплайном
                int_samples = (samples * 32767).astype(np.int16)

                # Разбиваем на chunk_size кусочки для корректной работы VAD
                for i in range(0, len(int_samples), self.chunk_size):
                    chunk = int_samples[i: i + self.chunk_size]
                    if len(chunk) < self.chunk_size // 2:
                        # Слишком маленький остаток — пропускаем
                        break
                    # Дополняем до chunk_size нулями если нужно
                    if len(chunk) < self.chunk_size:
                        chunk = np.pad(chunk, (0, self.chunk_size - len(chunk)))
                    self._process_system_chunk(chunk)

            self.system_capture.stop_recording()

        except Exception as e:
            import traceback
            print(f"[ERROR] Ошибка при захвате системного звука: {e}")
            traceback.print_exc()
    
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
