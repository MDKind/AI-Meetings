import os
import tarfile
import urllib.request
import numpy as np
from typing import Callable, List, NamedTuple, Optional

_MODELS_DIR = os.path.join(
    os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
    'AI Meetings', 'models', 'diarization'
)

_SEG_URL = (
    'https://github.com/k2-fsa/sherpa-onnx/releases/download/'
    'speaker-segmentation-models/'
    'sherpa-onnx-pyannote-segmentation-3-0.tar.bz2'
)
_EMB_URL = (
    'https://github.com/k2-fsa/sherpa-onnx/releases/download/'
    'speaker-recognition-models/'
    '3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx'
)


class DiarSegment(NamedTuple):
    speaker_id: int
    start: float   # seconds from recording start
    end: float     # seconds from recording start


def is_available() -> bool:
    try:
        import sherpa_onnx  # noqa
        return True
    except ImportError:
        return False


def _download(url: str, dest: str, progress_cb: Optional[Callable] = None):
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
    urllib.request.install_opener(opener)
    tmp = dest + '.tmp'
    try:
        def _reporthook(count, block, total):
            if progress_cb and total > 0:
                pct = min(count * block * 100 // total, 100)
                progress_cb(pct)
        urllib.request.urlretrieve(url, tmp, reporthook=_reporthook)
        os.replace(tmp, dest)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _ensure_models(status_cb: Optional[Callable[[str], None]] = None) -> tuple:
    """Returns (seg_model_path, emb_model_path). Downloads on first call."""
    os.makedirs(_MODELS_DIR, exist_ok=True)

    seg_model = os.path.join(
        _MODELS_DIR, 'sherpa-onnx-pyannote-segmentation-3-0', 'model.onnx'
    )
    emb_model = os.path.join(_MODELS_DIR, '3dspeaker_eres2net.onnx')

    if not os.path.exists(seg_model):
        if status_cb:
            status_cb('Скачивание модели сегментации (6 МБ)...')
        tar_path = os.path.join(_MODELS_DIR, 'seg.tar.bz2')
        _download(_SEG_URL, tar_path)
        with tarfile.open(tar_path, 'r:bz2') as tf:
            tf.extractall(_MODELS_DIR)
        os.remove(tar_path)

    if not os.path.exists(emb_model):
        if status_cb:
            status_cb('Скачивание модели эмбеддингов (~9 МБ)...')
        _download(_EMB_URL, emb_model)

    return seg_model, emb_model


def diarize(
    pcm_int16_bytes: bytes,
    sample_rate: int = 16000,
    num_speakers: int = -1,
    status_cb: Optional[Callable[[str], None]] = None,
) -> List[DiarSegment]:
    """
    Разделяет аудио по спикерам.

    Args:
        pcm_int16_bytes: сырой PCM int16 mono
        sample_rate: частота дискретизации (Гц)
        num_speakers: количество спикеров (-1 = авто)
        status_cb: вызывается с текстовыми статусами

    Returns:
        Список DiarSegment(speaker_id, start_sec, end_sec), отсортированный по start.
    """
    import sherpa_onnx

    seg_model, emb_model = _ensure_models(status_cb)

    if status_cb:
        status_cb('Инициализация диаризатора...')

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=seg_model
            )
        ),
        embedding=sherpa_onnx.OfflineSpeakerEmbeddingExtractorConfig(
            model=emb_model
        ),
        clustering=sherpa_onnx.OfflineSpeakerClusteringConfig(
            num_speakers=num_speakers,
            threshold=0.5,
        ),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )

    sd = sherpa_onnx.OfflineSpeakerDiarization(config)

    audio_f32 = (
        np.frombuffer(pcm_int16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    )

    if status_cb:
        status_cb('Анализ спикеров...')

    result = sd.process(audio_f32)

    return [
        DiarSegment(seg.speaker, seg.start, seg.end)
        for seg in result.sort_by_start_time()
    ]
