import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def isolate_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("HF_HUB_DISABLE_PROGRESS_BARS", raising=False)


def _make_cached_model(tmp_path, model_name="base"):
    model_dir = tmp_path / "MDelta Meetings" / "models" / f"faster-whisper-{model_name}"
    model_dir.mkdir(parents=True)
    return model_dir


def _fake_dl_factory(tmp_path, model_name="base"):
    """Returns a fake snapshot_download that writes model.bin so post-check passes."""
    def fake_dl(**kwargs):
        d = _make_cached_model(tmp_path, model_name)
        (d / "model.bin").write_bytes(b"x" * 100)
    return fake_dl


class TestFasterWhisperEnsureModel:

    def test_skips_download_when_model_cached(self, tmp_path):
        model_dir = _make_cached_model(tmp_path, "base")
        (model_dir / "model.bin").write_bytes(b"x" * 100)

        with patch("huggingface_hub.snapshot_download") as mock_dl:
            from src.speech_recognition import FasterWhisperBackend
            result = FasterWhisperBackend._ensure_model("base")

        mock_dl.assert_not_called()
        assert result == str(model_dir)

    def test_no_disable_tqdm_kwarg(self, tmp_path):
        """snapshot_download must NOT receive disable_tqdm — removed in huggingface_hub>=0.17."""
        captured = {}

        def fake_dl(**kwargs):
            captured.update(kwargs)
            _fake_dl_factory(tmp_path, "small")()

        with patch("huggingface_hub.snapshot_download", side_effect=fake_dl):
            from src.speech_recognition import FasterWhisperBackend
            FasterWhisperBackend._ensure_model("small")

        assert "disable_tqdm" not in captured

    def test_no_local_dir_use_symlinks_kwarg(self, tmp_path):
        """local_dir_use_symlinks removed in huggingface_hub>=0.17."""
        captured = {}

        def fake_dl(**kwargs):
            captured.update(kwargs)
            _fake_dl_factory(tmp_path, "base")()

        with patch("huggingface_hub.snapshot_download", side_effect=fake_dl):
            from src.speech_recognition import FasterWhisperBackend
            FasterWhisperBackend._ensure_model("base")

        assert "local_dir_use_symlinks" not in captured

    def test_progress_bar_env_var_set_during_download(self, tmp_path):
        env_during_call = []

        def fake_dl(**kwargs):
            env_during_call.append(os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS"))
            _fake_dl_factory(tmp_path, "base")()

        with patch("huggingface_hub.snapshot_download", side_effect=fake_dl):
            from src.speech_recognition import FasterWhisperBackend
            FasterWhisperBackend._ensure_model("base")

        assert env_during_call == ["1"]

    def test_env_var_removed_after_download_when_previously_unset(self, tmp_path):
        with patch("huggingface_hub.snapshot_download", side_effect=_fake_dl_factory(tmp_path, "base")):
            from src.speech_recognition import FasterWhisperBackend
            FasterWhisperBackend._ensure_model("base")

        assert "HF_HUB_DISABLE_PROGRESS_BARS" not in os.environ

    def test_env_var_restored_when_previously_set(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HF_HUB_DISABLE_PROGRESS_BARS", "0")

        with patch("huggingface_hub.snapshot_download", side_effect=_fake_dl_factory(tmp_path, "base")):
            from src.speech_recognition import FasterWhisperBackend
            FasterWhisperBackend._ensure_model("base")

        assert os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "0"

    def test_env_var_restored_even_on_download_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HF_HUB_DISABLE_PROGRESS_BARS", "previous")

        def failing_dl(**kwargs):
            raise RuntimeError("network error")

        with patch("huggingface_hub.snapshot_download", side_effect=failing_dl):
            from src.speech_recognition import FasterWhisperBackend
            with pytest.raises(RuntimeError):
                FasterWhisperBackend._ensure_model("base")

        assert os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "previous"

    def test_raises_if_model_bin_missing_after_download(self, tmp_path):
        def fake_dl(**kwargs):
            pass  # intentionally does not create model.bin

        with patch("huggingface_hub.snapshot_download", side_effect=fake_dl):
            from src.speech_recognition import FasterWhisperBackend
            with pytest.raises(RuntimeError, match="Не удалось скачать модель"):
                FasterWhisperBackend._ensure_model("base")

    def test_correct_repo_id_passed(self, tmp_path):
        captured = {}

        def fake_dl(**kwargs):
            captured.update(kwargs)
            _fake_dl_factory(tmp_path, "medium")()

        with patch("huggingface_hub.snapshot_download", side_effect=fake_dl):
            from src.speech_recognition import FasterWhisperBackend
            FasterWhisperBackend._ensure_model("medium")

        assert captured["repo_id"] == "Systran/faster-whisper-medium"


class TestSetModel:
    def _make_recognizer(self, model_name="base", language="ru"):
        from src.speech_recognition import SpeechRecognizer
        sr = SpeechRecognizer.__new__(SpeechRecognizer)
        sr.model_name = model_name
        sr._backend = MagicMock()
        sr._backend._language = language
        return sr

    def test_noop_if_same_model(self):
        from src.speech_recognition import SpeechRecognizer
        sr = self._make_recognizer("base")
        original_backend = sr._backend
        sr.set_model("base")
        assert sr._backend is original_backend
        assert sr.model_name == "base"

    def test_changes_model_name_and_uses_whisper_net(self):
        from src.speech_recognition import SpeechRecognizer
        sr = self._make_recognizer("base", "ru")
        mock_backend = MagicMock()

        def fake_close():
            sr._backend = None

        with patch("src.speech_recognition.WhisperNetBackend", return_value=mock_backend) as mock_cls:
            with patch.object(sr, "_ensure_temp_dir"):
                with patch.object(sr, "close", side_effect=fake_close):
                    sr.set_model("small")

        assert sr.model_name == "small"
        mock_cls.assert_called_once_with("small", "ru")
        assert sr._backend is mock_backend

    def test_falls_back_to_faster_whisper_when_whisper_net_fails(self):
        from src.speech_recognition import SpeechRecognizer
        sr = self._make_recognizer("base", "en")
        mock_backend = MagicMock()

        def fake_close():
            sr._backend = None

        with patch("src.speech_recognition.WhisperNetBackend", side_effect=RuntimeError("no exe")):
            with patch("src.speech_recognition.FasterWhisperBackend", return_value=mock_backend) as mock_cls:
                with patch.object(sr, "_ensure_temp_dir"):
                    with patch.object(sr, "close", side_effect=fake_close):
                        sr.set_model("medium")

        assert sr.model_name == "medium"
        mock_cls.assert_called_once_with("medium", "en")
        assert sr._backend is mock_backend
