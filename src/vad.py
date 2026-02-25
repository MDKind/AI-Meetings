"""
Voice Activity Detection (VAD) модуль.

Использует Silero VAD (нейросетевая модель) как основной метод,
с автоматическим fallback на RMS-пороговый детектор если Silero недоступен.

Silero VAD: https://github.com/snakers4/silero-vad
- Модель 1.8 MB, ~1 мс на чанк
- Специально обучена на переговорах и телефонных звонках
- Не требует настройки порогов
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)

# Пытаемся загрузить Silero VAD
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
    """

    # Silero VAD ожидает чанки строго 512 или 256 сэмплов при 16 kHz
    CHUNK_SAMPLES = 512

    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000):
        """
        Args:
            threshold: Порог вероятности речи [0..1]. 0.5 — сбалансированный.
                       Понизить до 0.3 для тихих голосов, повысить до 0.7 для шумных помещений.
            sample_rate: Частота дискретизации (только 16000 или 8000).
        """
        self.threshold = threshold
        self.sample_rate = sample_rate
        self._available = _try_load_silero()
        self._remainder = np.array([], dtype=np.float32)

    def is_available(self) -> bool:
        return self._available

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """
        Определяет, содержит ли аудиочанк речь.

        Args:
            audio_chunk: float32 numpy array [-1..1], любой длины.

        Returns:
            True если речь обнаружена.
        """
        if not self._available or _silero_model is None:
            return _rms_is_speech(audio_chunk)

        try:
            import torch

            # Добавляем остаток от предыдущего вызова
            audio = np.concatenate([self._remainder, audio_chunk.flatten()])

            # Обрабатываем кратными CHUNK_SAMPLES блоками
            speech_detected = False
            pos = 0
            while pos + self.CHUNK_SAMPLES <= len(audio):
                chunk = audio[pos: pos + self.CHUNK_SAMPLES]
                tensor = torch.from_numpy(chunk).unsqueeze(0)  # (1, 512)
                prob = _silero_model(tensor, self.sample_rate).item()
                if prob >= self.threshold:
                    speech_detected = True
                pos += self.CHUNK_SAMPLES

            # Сохраняем остаток для следующего вызова
            self._remainder = audio[pos:]

            return speech_detected

        except Exception as e:
            logger.debug(f"Silero VAD ошибка, fallback на RMS: {e}")
            return _rms_is_speech(audio_chunk)

    def reset(self):
        """Сбрасывает внутренний буфер (вызывать при старте новой записи)."""
        self._remainder = np.array([], dtype=np.float32)
        if self._available and _silero_model is not None:
            try:
                _silero_model.reset_states()
            except Exception:
                pass


class RmsVAD:
    """
    Простой RMS-пороговый детектор речи.
    Используется как fallback если Silero недоступен.
    """

    def __init__(self, threshold: int = 300):
        """
        Args:
            threshold: Порог RMS в единицах int16 (0..32767).
                       300 ≈ 0.9% от максимума — подходит для тихих помещений.
        """
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
    # Если float32 [-1..1] — масштабируем до int16 диапазона для сравнения
    if flat.dtype in (np.float32, np.float64):
        flat = (flat * 32767).astype(np.int16)
    return float(np.abs(flat).mean()) > threshold


def create_vad(threshold: float = 0.5, rms_threshold: int = 300,
               sample_rate: int = 16000) -> 'SileroVAD | RmsVAD':
    """
    Фабричная функция: возвращает Silero VAD если доступен, иначе RMS VAD.

    Args:
        threshold: Порог для Silero VAD (0..1)
        rms_threshold: Порог для RMS VAD (int16 единицы)
        sample_rate: Частота дискретизации

    Returns:
        SileroVAD или RmsVAD
    """
    vad = SileroVAD(threshold=threshold, sample_rate=sample_rate)
    if vad.is_available():
        return vad
    logger.info("Используется RMS VAD (Silero недоступен)")
    return RmsVAD(threshold=rms_threshold)
