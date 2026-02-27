import sounddevice as sd
import threading
import time
import numpy as np
from queue import Queue


class SystemAudioCapture:
    """
    Захват системного звука через WASAPI loopback (pyaudiowpatch).

    Ключевая особенность WASAPI loopback: stream.read() блокируется
    когда нет активного воспроизведения звука. Решение — держать
    silent output stream на том же устройстве (стандартный workaround
    используемый в NAudio, OBS и других приложениях).

    Fallback: Stereo Mix / Стереомикшер через sounddevice.
    """

    def __init__(self, sample_rate=16000, channels=1, chunk_size=1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.is_recording = False
        self.data_queue = Queue()

        self._pyaudio_instance = None
        self._loopback_stream = None
        self._silence_stream = None   # output stream для keepalive

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_recording(self, device_index=None):
        """
        Начинает захват системного звука.

        Приоритет:
          1. WASAPI loopback для выбранного output устройства
          2. Любой доступный WASAPI loopback
          3. Stereo Mix / Стереомикшер
          4. Генератор тишины

        Args:
            device_index: Индекс output устройства выбранного пользователем
        """
        self.is_recording = True
        self.data_queue = Queue()

        print("[SystemAudio] Запуск захвата системного звука...")

        if self._try_wasapi_loopback(device_index):
            return
        if self._try_stereo_mix():
            return

        print("[SystemAudio] Захват системного звука недоступен.")
        print("[SystemAudio] Включите Stereo Mix в настройках Windows или используйте VB-Cable.")
        threading.Thread(target=self._generate_silence, daemon=True).start()

    def stop_recording(self):
        self.is_recording = False
        # Даём читающему потоку время завершиться
        time.sleep(0.2)

        for attr in ('_loopback_stream', '_silence_stream'):
            stream = getattr(self, attr, None)
            setattr(self, attr, None)
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass

        # terminate() намеренно не вызываем — вызывает segfault если
        # daemon-поток ещё держит ссылку на объекты PyAudio.
        self._pyaudio_instance = None
        print("[SystemAudio] Запись системного звука остановлена.")

    def get_audio_data(self):
        """Возвращает накопленные аудиоданные (float32, mono) или None."""
        if self.data_queue.empty():
            return None
        chunks = []
        while not self.data_queue.empty():
            chunks.append(self.data_queue.get())
        return np.concatenate(chunks) if chunks else None

    # ------------------------------------------------------------------
    # WASAPI loopback (pyaudiowpatch)
    # ------------------------------------------------------------------

    def _try_wasapi_loopback(self, preferred_output_index=None) -> bool:
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            print("[SystemAudio] pyaudiowpatch не установлен, пропуск WASAPI loopback")
            return False

        try:
            p = pyaudio.PyAudio()
            loopbacks = list(p.get_loopback_device_info_generator())

            if not loopbacks:
                print("[SystemAudio] WASAPI loopback устройства не найдены")
                return False

            # Выбираем loopback соответствующий preferred_output_index
            target = self._match_loopback(p, loopbacks, preferred_output_index)
            print(f"[SystemAudio] WASAPI loopback: {target['name']}")

            rate = int(target['defaultSampleRate'])
            ch = min(target['maxInputChannels'], 2)

            self._pyaudio_instance = p

            # Silence keeper: output stream на том же устройстве.
            # Без него stream.read() блокируется при тишине (фундаментальное
            # поведение WASAPI — нет рендеринга = нет данных в capture буфере).
            silence_out_index = self._find_output_for_loopback(p, target, preferred_output_index)
            if silence_out_index is not None:
                try:
                    self._silence_stream = p.open(
                        format=pyaudio.paFloat32,
                        channels=ch,
                        rate=rate,
                        output=True,
                        output_device_index=silence_out_index,
                        frames_per_buffer=self.chunk_size,
                    )
                    threading.Thread(
                        target=self._write_silence,
                        args=(ch,),
                        daemon=True,
                    ).start()
                    print(f"[SystemAudio] Silence keeper запущен (output index={silence_out_index})")
                except Exception as e:
                    print(f"[SystemAudio] Silence keeper не запущен: {e}")

            # Loopback capture stream
            self._loopback_stream = p.open(
                format=pyaudio.paFloat32,
                channels=ch,
                rate=rate,
                frames_per_buffer=self.chunk_size,
                input=True,
                input_device_index=target['index'],
            )
            print(f"[SystemAudio] Capture stream открыт (rate={rate}, ch={ch})")

            threading.Thread(
                target=self._read_wasapi_loopback,
                args=(rate, ch),
                daemon=True,
            ).start()
            return True

        except Exception as e:
            print(f"[SystemAudio] WASAPI loopback ошибка: {e}")
            return False

    def _match_loopback(self, p, loopbacks, preferred_output_index):
        """
        Выбирает loopback устройство соответствующее preferred_output_index.

        Алгоритм: имена устройств могут быть в сломанной кодировке, поэтому
        не полагаемся на сравнение строк. Вместо этого:
        1. Находим positional rank preferred_output_index среди WASAPI output устройств.
        2. Берём loopback с тем же rank (они идут в одном порядке).
        """
        if preferred_output_index is None:
            return loopbacks[0]

        try:
            # Получаем список всех WASAPI output устройств в порядке индексов
            wasapi_hostapi = None
            for i in range(p.get_host_api_count()):
                api = p.get_host_api_info_by_index(i)
                if 'wasapi' in api['name'].lower():
                    wasapi_hostapi = i
                    break

            wasapi_outputs = []
            for i in range(p.get_device_count()):
                d = p.get_device_info_by_index(i)
                if d['maxOutputChannels'] > 0 and d.get('hostApi') == wasapi_hostapi:
                    wasapi_outputs.append(i)

            # Находим WASAPI output соответствующий preferred_output_index по имени
            # (все hostapi дублируют одни и те же устройства с одинаковыми именами)
            preferred_info = p.get_device_info_by_index(preferred_output_index)
            preferred_name_stripped = preferred_info['name'][:12]  # первые 12 символов как ключ

            matched_rank = None
            for rank, wasapi_idx in enumerate(wasapi_outputs):
                wd = p.get_device_info_by_index(wasapi_idx)
                if wd['name'][:12] == preferred_name_stripped:
                    matched_rank = rank
                    break

            if matched_rank is not None and matched_rank < len(loopbacks):
                print(f"[SystemAudio] Matched loopback rank={matched_rank}: {loopbacks[matched_rank]['name']}")
                return loopbacks[matched_rank]

        except Exception as e:
            print(f"[SystemAudio] _match_loopback fallback: {e}")

        return loopbacks[0]

    def _find_output_for_loopback(self, p, loopback_dev, preferred_output_index):
        """
        Находит WASAPI output device index для silence keeper.
        Loopback называется как "[Name] [Loopback]", output — "[Name]".
        Ищем WASAPI output у которого name совпадает с loopback без суффикса.
        """
        lb_name = loopback_dev['name']  # включает " [Loopback]"
        lb_base = lb_name[:12]          # первые 12 символов как ключ (обходим кодировку)

        wasapi_hostapi = None
        for i in range(p.get_host_api_count()):
            api = p.get_host_api_info_by_index(i)
            if 'wasapi' in api['name'].lower():
                wasapi_hostapi = i
                break

        for i in range(p.get_device_count()):
            try:
                d = p.get_device_info_by_index(i)
                if d['maxOutputChannels'] > 0 and d.get('hostApi') == wasapi_hostapi:
                    if d['name'][:12] == lb_base:
                        return i
            except Exception:
                pass

        # fallback: preferred_output_index если это output устройство
        if preferred_output_index is not None:
            try:
                d = p.get_device_info_by_index(preferred_output_index)
                if d['maxOutputChannels'] > 0:
                    return preferred_output_index
            except Exception:
                pass
        return None

    def _write_silence(self, channels: int):
        """Пишет нули в output stream чтобы WASAPI render clock работал."""
        silence = (np.zeros(self.chunk_size * channels, dtype=np.float32)).tobytes()
        try:
            while self.is_recording:
                stream = self._silence_stream
                if stream is None:
                    break
                try:
                    stream.write(silence)
                except Exception:
                    break
        except Exception as e:
            print(f"[SystemAudio] _write_silence завершён: {e}")

    def _read_wasapi_loopback(self, rate: int, channels: int):
        """Читает данные из WASAPI loopback потока в blocking режиме."""
        try:
            while self.is_recording:
                stream = self._loopback_stream
                if stream is None:
                    break
                try:
                    raw = stream.read(self.chunk_size, exception_on_overflow=False)
                except Exception as e:
                    if self.is_recording:
                        print(f"[SystemAudio] loopback read error: {e}")
                    break

                audio = np.frombuffer(raw, dtype=np.float32)
                if channels > 1:
                    audio = audio.reshape(-1, channels).mean(axis=1)

                # Линейный ресэмплинг до target sample_rate
                if rate != self.sample_rate and rate > 0:
                    new_len = int(len(audio) * self.sample_rate / rate)
                    if new_len > 0:
                        indices = np.linspace(0, len(audio) - 1, new_len)
                        audio = np.interp(indices, np.arange(len(audio)), audio)

                self.data_queue.put(audio.reshape(-1, 1).astype(np.float32))
        except Exception as e:
            print(f"[SystemAudio] _read_wasapi_loopback завершён: {e}")

    # ------------------------------------------------------------------
    # Stereo Mix fallback (sounddevice)
    # ------------------------------------------------------------------

    def _try_stereo_mix(self) -> bool:
        """
        Ищет Stereo Mix / Стереомикшер среди input устройств.
        Имена устройств приходят в Unicode (кириллица), ищем по подстроке.
        """
        keywords_en = ("stereo mix", "what u hear", "cable output")
        # Unicode codepoints для "стереомикшер" и "стереомикс"
        keywords_ru = ("стереомикшер", "стерео микс", "стереомикс")

        try:
            devices = sd.query_devices()
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    name = device['name']
                    name_lower = name.lower()
                    if (any(kw in name_lower for kw in keywords_en) or
                            any(kw in name_lower for kw in keywords_ru)):
                        print(f"[SystemAudio] Найден Stereo Mix: '{name}' (индекс {i})")
                        threading.Thread(
                            target=self._record_with_sounddevice,
                            args=(i,),
                            daemon=True,
                        ).start()
                        return True
        except Exception as e:
            print(f"[SystemAudio] Ошибка поиска Stereo Mix: {e}")
        return False

    def _record_with_sounddevice(self, device_index):
        try:
            def callback(indata, frames, t, status):
                if status:
                    print(f"[SystemAudio] sounddevice status: {status}")
                self.data_queue.put(indata.copy())

            with sd.InputStream(
                device=device_index,
                channels=self.channels,
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                callback=callback,
            ):
                print(f"[SystemAudio] Запись через sounddevice (Stereo Mix, индекс {device_index})...")
                while self.is_recording:
                    time.sleep(0.1)
        except Exception as e:
            print(f"[SystemAudio] sounddevice ошибка: {e}")

    # ------------------------------------------------------------------
    # Silence fallback
    # ------------------------------------------------------------------

    def _generate_silence(self):
        silence = np.zeros((self.chunk_size, 1), dtype=np.float32)
        while self.is_recording:
            time.sleep(0.5)
            self.data_queue.put(silence.copy())
