import sys
import os
import pytest
import numpy as np
from unittest.mock import MagicMock, patch, call

import src.diarization as diar
from src.diarization import DiarSegment


# ── is_available ──────────────────────────────────────────────────────────────

def test_is_available_true():
    mock_sherpa = MagicMock()
    with patch.dict(sys.modules, {"sherpa_onnx": mock_sherpa}):
        assert diar.is_available() is True


def test_is_available_false():
    with patch.dict(sys.modules, {"sherpa_onnx": None}):
        assert diar.is_available() is False


# ── _ensure_models ────────────────────────────────────────────────────────────

def test_ensure_models_skips_download_when_present(tmp_path, monkeypatch):
    seg_path = tmp_path / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
    emb_path = tmp_path / "3dspeaker_eres2net.onnx"
    seg_path.parent.mkdir(parents=True)
    seg_path.touch()
    emb_path.touch()

    monkeypatch.setattr(diar, "_MODELS_DIR", str(tmp_path))

    with patch("src.diarization._download") as mock_dl:
        s, e = diar._ensure_models()

    mock_dl.assert_not_called()
    assert s == str(seg_path)
    assert e == str(emb_path)


def test_ensure_models_calls_status_cb_for_missing_seg(tmp_path, monkeypatch):
    monkeypatch.setattr(diar, "_MODELS_DIR", str(tmp_path))
    # seg model is missing; emb model is present
    emb_path = tmp_path / "3dspeaker_eres2net.onnx"
    emb_path.touch()

    status_calls = []

    def fake_download(url, dest, progress_cb=None):
        open(dest, "wb").close()  # create the file so os.remove succeeds later
        seg_dir = tmp_path / "sherpa-onnx-pyannote-segmentation-3-0"
        seg_dir.mkdir(exist_ok=True)
        (seg_dir / "model.onnx").touch()

    with patch("src.diarization._download", side_effect=fake_download):
        with patch("tarfile.open"):
            diar._ensure_models(status_cb=lambda msg: status_calls.append(msg))

    assert any("сегментации" in c.lower() for c in status_calls)


# ── diarize ───────────────────────────────────────────────────────────────────

def _make_sherpa_mock(segments):
    """Build a minimal sherpa_onnx module mock that returns `segments` from diarize."""
    seg_obj_list = []
    for sid, start, end in segments:
        s = MagicMock()
        s.speaker = sid
        s.start = start
        s.end = end
        seg_obj_list.append(s)

    mock_result = MagicMock()
    mock_result.sort_by_start_time.return_value = seg_obj_list

    mock_sd_instance = MagicMock()
    mock_sd_instance.process.return_value = mock_result

    mock_sherpa = MagicMock()
    mock_sherpa.OfflineSpeakerDiarization.return_value = mock_sd_instance

    return mock_sherpa


def test_diarize_returns_diar_segments():
    sherpa = _make_sherpa_mock([(0, 0.0, 2.0), (1, 2.5, 5.0)])
    pcm = (np.zeros(16000, dtype=np.int16)).tobytes()

    with patch.dict(sys.modules, {"sherpa_onnx": sherpa}):
        with patch("src.diarization._ensure_models", return_value=("/seg.onnx", "/emb.onnx")):
            result = diar.diarize(pcm)

    assert len(result) == 2
    assert result[0] == DiarSegment(speaker_id=0, start=0.0, end=2.0)
    assert result[1] == DiarSegment(speaker_id=1, start=2.5, end=5.0)


def test_diarize_empty_audio_returns_empty():
    sherpa = _make_sherpa_mock([])
    pcm = (np.zeros(8000, dtype=np.int16)).tobytes()

    with patch.dict(sys.modules, {"sherpa_onnx": sherpa}):
        with patch("src.diarization._ensure_models", return_value=("/seg.onnx", "/emb.onnx")):
            result = diar.diarize(pcm)

    assert result == []


def test_diarize_calls_status_callbacks():
    sherpa = _make_sherpa_mock([(0, 0.0, 3.0)])
    pcm = (np.zeros(16000, dtype=np.int16)).tobytes()
    status_calls = []

    with patch.dict(sys.modules, {"sherpa_onnx": sherpa}):
        with patch("src.diarization._ensure_models", return_value=("/seg.onnx", "/emb.onnx")):
            diar.diarize(pcm, status_cb=lambda msg: status_calls.append(msg))

    assert any("Инициализация" in c for c in status_calls)
    assert any("Анализ" in c for c in status_calls)


def test_diarize_converts_pcm_correctly():
    """Float32 audio passed to sherpa must be int16/32768 normalised."""
    sherpa = _make_sherpa_mock([(0, 0.0, 1.0)])
    pcm_i16 = np.array([32767, -32768, 0], dtype=np.int16).tobytes()

    captured = {}

    def fake_process(audio_f32):
        captured["audio"] = audio_f32
        result = MagicMock()
        result.sort_by_start_time.return_value = []
        return result

    sherpa.OfflineSpeakerDiarization.return_value.process.side_effect = fake_process

    with patch.dict(sys.modules, {"sherpa_onnx": sherpa}):
        with patch("src.diarization._ensure_models", return_value=("/seg.onnx", "/emb.onnx")):
            diar.diarize(pcm_i16)

    arr = captured["audio"]
    assert arr.dtype == np.float32
    assert abs(arr[0] - (32767 / 32768.0)) < 1e-4
    assert abs(arr[1] - (-32768 / 32768.0)) < 1e-4
    assert arr[2] == 0.0
