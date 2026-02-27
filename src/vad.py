"""
Voice Activity Detection (VAD) модуль.

Использует Silero VAD (нейросетевая модель) как основной метод,
с автоматическим fallback на RMS-пороговый детектор если Silero недоступен.

Silero VAD: https://github.com/snakers4/silero-vad
- Модель 1.8 MB, ~1 мс на чанк
- Специально обучена на переговорах и телефонных звонках
- Не требует настройки порогов
"""

import copy
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Загрузка Silero VAD — один раз, потом копируем для каждого инстанса
_silero_model = None
_silero_available = False


def _try_load_silero():
    """Ленивая загрузка Silero VAD при первом обращении."""
    global _silero_model, _silero_available
    if _silero_available or _silero_model is not None:
        return _silero_available
    try:
        import torch
        model, _ = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            verbose=False
        )
        model.eval()
        _silero_model = model
        _silero_available = True
        logger.info("Silero VAD загружен успешно")
    except Exception as e:
        logger.warning(f"Silero VAD недоступен, используется RMS-детектор: {e}")
        _silero_available = False
    return _silero_available


class SileroVAD:
    """
    Нейросетевой детектор речи на основе Silero VAD.
    Принимает чанки float32 16 kHz моно.

    Каждый инстанс держит собственную копию модели — полная изоляция
    LSTM-состояния между потоками без локов.
    """

    # Silero VAD ожидает чанки строго 512 или 256 сэмплов при 16 kHz
    CHUNK_SAMPLES = 512

    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000):
        self.threshold = threshold
        self.sample_rate = sample_rate
        self._remainder = np.array([], dtype=np.float32)

        self._available = _try_load_silero()
        # Каждый инстанс получает независимую копию модели (свой LSTM state)
        if self._available and _silero_model is not None:
            try:
                self._model = copy.deepcopy(_silero_model)
                self._model.eval()
            except Exception as e:
                logger.warning(f"Silero deepcopy не удался, используется общая модель: {e}")
                self._model = _silero_model
        else:
            self._model = None

    def is_available(self) -> bool:
        return self._available and self._model is not None

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """
        Определяет, содержит ли аудиочанк речь.

        Args:
            audio_chunk: float32 numpy array [-1..1], любой длины.

        Returns:
            True если речь обнаружена.
        """
        if not self.is_available():
            return _rms_is_speech(audio_chunk)

        try:
            import torch

            audio = np.concatenate([self._remainder, audio_chunk.flatten()])

            speech_detected = False
            pos = 0
            # Нет глобального лока — у каждого инстанса своя модель и свой LSTM state
            while pos + self.CHUNK_SAMPLES <= len(audio):
                chunk = audio[pos: pos + self.CHUNK_SAMPLES]
                tensor = torch.from_numpy(chunk).unsqueeze(0)  # (1, 512)
                prob = self._model(tensor, self.sample_rate).item()
                if prob >= self.threshold:
                    speech_detected = True
                pos += self.CHUNK_SAMPLES

            self._remainder = audio[pos:]
            return speech_detected

        except Exception as e:
            logger.debug(f"Silero VAD ошибка, fallback на RMS: {e}")
            return _rms_is_speech(audio_chunk)

    def reset(self):
        """Сбрасывает внутренний буфер и LSTM-состояние."""
        self._remainder = np.array([], dtype=np.float32)
        if self._model is not None:
            try:
                self._model.reset_states()
            except Exception:
                pass


class RmsVAD:
    """
    Простой RMS-пороговый детектор речи.
    Используется как fallback если Silero недоступен.
    """

    def __init__(self, threshold: int = 300):
        self.threshold = threshold

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        return _rms_is_speech(audio_chunk, self.threshold)

    def reset(self):
        pass


def _rms_is_speech(audio_chunk: np.ndarray, threshold: int = 300) -> bool:
    """Вычисляет RMS и сравнивает с порогом."""
    if audio_chunk is None or len(audio_chunk) == 0:
        return False
    flat = audio_chunk.flatten()
    if flat.dtype in (np.float32, np.float64):
        flat = (flat * 32767).astype(np.int16)
    return float(np.abs(flat).mean()) > threshold


def create_vad(threshold: float = 0.5, rms_threshold: int = 300,
               sample_rate: int = 16000) -> 'SileroVAD | RmsVAD':
    """
    Фабричная функция: возвращает Silero VAD если доступен, иначе RMS VAD.
    """
    vad = SileroVAD(threshold=threshold, sample_rate=sample_rate)
    if vad.is_available():
        return vad
    logger.info("Используется RMS VAD (Silero недоступен)")
    return RmsVAD(threshold=rms_threshold)
