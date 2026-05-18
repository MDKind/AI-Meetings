import sounddevice as sd
import threading
import time
import numpy as np
from collections import deque
from queue import Queue
from datetime import datetime
from utils.config import AUDIO_SETTINGS
from src.system_audio_capture import SystemAudioCapture
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
        self.silence_duration = AUDIO_SETTINGS.get('silence_duration_vad', 1.2)
        self.min_segment_duration = AUDIO_SETTINGS.get('min_segment_duration', 0.8)
        self.max_segment_duration = AUDIO_SETTINGS.get('max_segment_duration', 20.0)
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

        # Pre-roll: ~0.3 сек чанков до момента обнаружения речи
        # Silero VAD нужно несколько чанков для "разогрева" LSTM, начало фразы теряется
        _preroll_chunks = max(1, int(0.3 * rate / chunk_size))
        self._preroll: deque = deque(maxlen=_preroll_chunks)
        self._sys_preroll: deque = deque(maxlen=_preroll_chunks)

        # Отдельный VAD + состояние для системного звука (изолировано от mic-пути)
        self._sys_vad = create_vad(threshold=0.5, rms_threshold=silence_threshold, sample_rate=rate)
        self._sys_frames: list[bytes] = []
        self._sys_speaking = False
        self._sys_silent_chunks = 0
        self._sys_segment_start: datetime | None = None

        self._session_pcm: bytearray = bytearray()
        self._session_start: datetime | None = None

    @staticmethod
    def _get_wasapi_devices():
        """
        Возвращает только WASAPI-устройства (без дублей MME/DirectSound/WDM).
        Также возвращает индексы системных default-устройств.

        Returns:
            (devices, default_input_idx, default_output_idx)
            devices: список dict из sd.query_devices() с добавленным полем 'sd_index'
        """
        try:
            host_apis = sd.query_hostapis()
            wasapi_api = next((a for a in host_apis if 'WASAPI' in a['name']), None)
            wasapi_idx = wasapi_api['index'] if wasapi_api else None
        except Exception:
            wasapi_idx = None

        all_devices = sd.query_devices()
        try:
            default_input_idx = sd.default.device[0]
            default_output_idx = sd.default.device[1]
        except Exception:
            default_input_idx = None
            default_output_idx = None

        result = []
        for i, dev in enumerate(all_devices):
            # Показываем только WASAPI устройства (если WASAPI доступен)
            if wasapi_idx is not None and dev.get('hostapi') != wasapi_idx:
                continue
            dev = dict(dev)
            dev['sd_index'] = i
            result.append(dev)

        return result, default_input_idx, default_output_idx

    def list_input_devices(self):
        """
        Возвращает список устройств ввода (только WASAPI, без дублей).
        Returns: list of (index, display_name, device_type)
        """
        devices, default_input, _ = self._get_wasapi_devices()
        result = []
        for dev in devices:
            if dev['max_input_channels'] <= 0:
                continue
            name = dev['name']
            idx = dev['sd_index']
            is_default = (idx == default_input)
            suffix = " [по умолчанию]" if is_default else ""
            if "stereo mix" in name.lower() or "стереомикшер" in name.lower() or "what u hear" in name.lower():
                result.append((idx, f"{name} (Системный звук){suffix}", "system_sound"))
            else:
                result.append((idx, f"{name}{suffix}", "microphone"))
        return result

    def list_output_devices(self):
        """
        Возвращает список устройств вывода (только WASAPI, без дублей).
        Returns: list of (index, display_name, device_type)
        """
        devices, _, default_output = self._get_wasapi_devices()
        result = []
        for dev in devices:
            if dev['max_output_channels'] <= 0:
                continue
            name = dev['name']
            idx = dev['sd_index']
            is_default = (idx == default_output)
            suffix = " [по умолчанию]" if is_default else ""
            result.append((idx, f"{name}{suffix}", "output"))
        return result
    
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
                # Добавляем pre-roll чтобы не потерять начало фразы
                self.current_frames.extend(self._preroll)
            self._preroll.clear()
            self.current_frames.append(data)

            max_chunks = int(self.rate / self.chunk_size * self.max_segment_duration)
            if len(self.current_frames) >= max_chunks:
                self._flush_segment(speaker=speaker)
        else:
            self._preroll.append(data)
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
        # Фильтруем слишком короткие сегменты — Whisper даёт галлюцинации на них
        min_chunks = int(self.rate / self.chunk_size * self.min_segment_duration)
        if len(self.current_frames) < min_chunks:
            self.current_frames = []
            self.speaking = False
            self._segment_start_time = None
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
        self._segment_start_time = None
        self.streams = []

        # Сбрасываем состояние mic и system аудио
        self._preroll.clear()
        self._sys_frames = []
        self._sys_speaking = False
        self._sys_silent_chunks = 0
        self._sys_segment_start = None
        self._sys_preroll.clear()
        if hasattr(self._sys_vad, 'reset'):
            self._sys_vad.reset()
        if hasattr(self._vad, 'reset'):
            self._vad.reset()

        self._session_pcm = bytearray()
        self._session_start = datetime.now()

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
                self._session_pcm.extend(chunk.flatten().tobytes())
                self._process_audio_data(chunk, speaker="local")
            except Exception:
                pass
    
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
                # Добавляем pre-roll чтобы не потерять начало фразы
                self._sys_frames.extend(self._sys_preroll)
            self._sys_preroll.clear()
            self._sys_frames.append(data)
            if len(self._sys_frames) >= max_chunks:
                self._flush_sys_segment()
        else:
            self._sys_preroll.append(data)
            self._sys_silent_chunks += 1
            if self._sys_speaking and self._sys_silent_chunks > silence_chunks_threshold:
                self._flush_sys_segment()
            elif self._sys_speaking:
                self._sys_frames.append(data)

    def _flush_sys_segment(self):
        if not self._sys_frames:
            return
        min_chunks = int(self.rate / self.chunk_size * self.min_segment_duration)
        if len(self._sys_frames) < min_chunks:
            self._sys_frames = []
            self._sys_speaking = False
            self._sys_silent_chunks = 0
            self._sys_segment_start = None
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
    
    @property
    def session_pcm(self) -> bytes:
        return bytes(self._session_pcm)

    @property
    def session_start(self):
        return self._session_start

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
