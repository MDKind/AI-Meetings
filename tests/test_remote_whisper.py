"""Тесты RemoteWhisperBackend и выбора источника STT в SpeechRecognizer."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def isolate_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


def _resp(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


class TestRemoteWhisperBackend:

    def test_requires_base_url(self):
        from src.speech_recognition import RemoteWhisperBackend
        with pytest.raises(ValueError):
            RemoteWhisperBackend("", "whisper-1", "ru")

    def test_probe_failure_raises_runtime_error(self):
        from src.speech_recognition import RemoteWhisperBackend
        with patch("requests.get", side_effect=ConnectionError("refused")):
            with pytest.raises(RuntimeError, match="недоступен"):
                RemoteWhisperBackend("http://127.0.0.1:9999/v1", "whisper-1", "ru")

    def test_transcribe_posts_wav_and_returns_text(self):
        from src.speech_recognition import RemoteWhisperBackend
        with patch("requests.get", return_value=_resp({"data": []})):
            backend = RemoteWhisperBackend(
                "http://srv:8000/v1/", "faster-whisper-large-v3", "ru", api_key="sk-x")

        with patch("requests.post", return_value=_resp({"text": " Привет мир "})) as mock_post:
            text = backend.transcribe(b"RIFFxxxx")

        assert text == "Привет мир"
        args, kwargs = mock_post.call_args
        assert args[0] == "http://srv:8000/v1/audio/transcriptions"
        assert kwargs["data"]["model"] == "faster-whisper-large-v3"
        assert kwargs["data"]["language"] == "ru"
        assert kwargs["headers"] == {"Authorization": "Bearer sk-x"}
        assert kwargs["files"]["file"][1] == b"RIFFxxxx"

    def test_no_auth_header_without_key(self):
        from src.speech_recognition import RemoteWhisperBackend
        with patch("requests.get", return_value=_resp({"data": []})):
            backend = RemoteWhisperBackend("http://srv:8000/v1", "whisper-1", "")
        with patch("requests.post", return_value=_resp({"text": "ok"})) as mock_post:
            backend.transcribe(b"x")
        assert mock_post.call_args.kwargs["headers"] == {}
        # без языка параметр language не передаётся
        assert "language" not in mock_post.call_args.kwargs["data"]

    def test_set_language(self):
        from src.speech_recognition import RemoteWhisperBackend
        with patch("requests.get", return_value=_resp({"data": []})):
            backend = RemoteWhisperBackend("http://srv:8000/v1", "whisper-1", "ru")
        backend.set_language("en")
        assert backend.language == "en"
        backend.set_language(None)
        assert backend.language == ""


class TestFetchRemoteWhisperModels:

    def test_returns_model_ids(self):
        from src.speech_recognition import fetch_remote_whisper_models
        payload = {"data": [{"id": "whisper-large-v3"}, {"id": "whisper-base"}]}
        with patch("requests.get", return_value=_resp(payload)) as mock_get:
            models = fetch_remote_whisper_models("http://srv:8000/v1", "key")
        assert models == ["whisper-large-v3", "whisper-base"]
        assert mock_get.call_args.args[0] == "http://srv:8000/v1/models"
        assert mock_get.call_args.kwargs["headers"] == {"Authorization": "Bearer key"}

    def test_empty_base_url_returns_empty(self):
        from src.speech_recognition import fetch_remote_whisper_models
        assert fetch_remote_whisper_models("") == []


class TestSpeechRecognizerSourceSelection:

    def _bare(self):
        from src.speech_recognition import SpeechRecognizer
        sr = SpeechRecognizer.__new__(SpeechRecognizer)
        sr.model_name = "base"
        sr._backend = MagicMock()
        sr._backend._language = "ru"
        return sr

    def test_remote_mode_uses_remote_backend(self):
        sr = self._bare()
        sr.mode = "remote"
        sr.remote_base_url = "http://srv:8000/v1"
        sr.remote_api_key = ""
        sr.remote_model = "whisper-1"
        mock_backend = MagicMock()
        with patch("src.speech_recognition.RemoteWhisperBackend", return_value=mock_backend) as cls:
            backend = sr._build_backend("base", "ru")
        assert backend is mock_backend
        cls.assert_called_once_with("http://srv:8000/v1", "whisper-1", "ru", "")

    def test_remote_failure_falls_back_to_local_when_model_cached(self):
        sr = self._bare()
        sr.mode = "remote"
        sr.remote_base_url = "http://srv:8000/v1"
        local_backend = MagicMock()
        with patch("src.speech_recognition.RemoteWhisperBackend", side_effect=RuntimeError("down")):
            with patch.object(type(sr), "_local_model_cached", staticmethod(lambda m: True)):
                with patch("src.speech_recognition.WhisperNetBackend", return_value=local_backend):
                    backend = sr._build_backend("base", "ru")
        assert backend is local_backend

    def test_remote_failure_without_cached_model_raises(self):
        """Без скачанной локальной модели ошибка сервера не приводит к скрытой загрузке."""
        sr = self._bare()
        sr.mode = "remote"
        sr.remote_base_url = "http://srv:8000/v1"
        with patch("src.speech_recognition.RemoteWhisperBackend", side_effect=RuntimeError("down")):
            with pytest.raises(RuntimeError, match="настройках"):
                sr._build_backend("base", "ru")

    def test_configure_source_switches_to_remote(self):
        sr = self._bare()
        remote_backend = MagicMock()

        def fake_close():
            sr._backend = None

        with patch("src.speech_recognition.RemoteWhisperBackend", return_value=remote_backend) as cls:
            with patch.object(sr, "_ensure_temp_dir"):
                with patch.object(sr, "close", side_effect=fake_close):
                    sr.configure_source("remote", "http://srv:8000/v1", "k", "whisper-1")

        assert sr.mode == "remote"
        assert sr._backend is remote_backend
        cls.assert_called_once_with("http://srv:8000/v1", "whisper-1", "ru", "k")

    def test_configure_source_noop_when_unchanged(self):
        sr = self._bare()
        sr.mode = "local"
        original = sr._backend
        with patch.object(sr, "close") as mock_close:
            sr.configure_source("local")
        mock_close.assert_not_called()
        assert sr._backend is original

    def test_active_backend_name(self):
        from src.speech_recognition import SpeechRecognizer, RemoteWhisperBackend
        sr = self._bare()
        with patch("requests.get", return_value=_resp({"data": []})):
            sr._backend = RemoteWhisperBackend("http://srv:8000/v1", "m", "ru")
        assert "Remote" in sr.active_backend_name


class TestLazyInitialization:
    """Ленивая инициализация: модель не скачивается при старте приложения."""

    def _bare(self):
        from src.speech_recognition import SpeechRecognizer
        import threading
        sr = SpeechRecognizer.__new__(SpeechRecognizer)
        sr.model_name = "base"
        sr._backend = None
        sr._backend_lock = threading.Lock()
        return sr

    def test_init_defers_when_local_model_not_cached(self, tmp_path):
        from src.speech_recognition import SpeechRecognizer
        with patch.object(SpeechRecognizer, "_build_backend") as mock_build:
            sr = SpeechRecognizer(model_name="base")
        mock_build.assert_not_called()
        assert sr.is_ready is False

    def test_init_preloads_when_local_model_cached(self, tmp_path):
        from src.speech_recognition import SpeechRecognizer
        ggml = tmp_path / "MDelta Meetings" / "models"
        ggml.mkdir(parents=True)
        (ggml / "ggml-base.bin").write_bytes(b"x" * 10)
        backend = MagicMock()
        with patch.object(SpeechRecognizer, "_build_backend", return_value=backend) as mock_build:
            sr = SpeechRecognizer(model_name="base")
        mock_build.assert_called_once()
        assert sr.is_ready is True

    def test_init_defers_in_remote_mode(self, tmp_path):
        from src.speech_recognition import SpeechRecognizer
        with patch.object(SpeechRecognizer, "_build_backend") as mock_build:
            sr = SpeechRecognizer(model_name="base", mode="remote",
                                  remote_base_url="http://srv:8000/v1")
        mock_build.assert_not_called()
        assert sr.is_ready is False

    def test_ensure_ready_builds_backend_once(self):
        sr = self._bare()
        sr.mode = "local"
        backend = MagicMock()
        statuses = []
        with patch.object(sr, "_build_backend", return_value=backend) as mock_build:
            with patch.object(sr, "_ensure_temp_dir"):
                sr.ensure_ready(status_cb=statuses.append)
                sr.ensure_ready(status_cb=statuses.append)  # второй вызов — noop
        mock_build.assert_called_once()
        assert sr.is_ready is True
        assert len(statuses) == 1 and "base" in statuses[0]

    def test_ensure_ready_propagates_error(self):
        sr = self._bare()
        sr.mode = "remote"
        sr.remote_base_url = ""
        with patch.object(sr, "_build_backend", side_effect=RuntimeError("не настроен")):
            with patch.object(sr, "_ensure_temp_dir"):
                with pytest.raises(RuntimeError, match="не настроен"):
                    sr.ensure_ready()
        assert sr.is_ready is False

    def test_set_model_deferred_does_not_build(self):
        sr = self._bare()
        with patch.object(sr, "_build_backend") as mock_build:
            sr.set_model("large-v3")
        mock_build.assert_not_called()
        assert sr.model_name == "large-v3"
        assert sr.is_ready is False

    def test_configure_source_deferred_stores_without_building(self):
        sr = self._bare()
        sr.mode = "local"
        sr.remote_base_url = ""
        sr.remote_api_key = ""
        sr.remote_model = "whisper-1"
        with patch.object(sr, "_build_backend") as mock_build:
            sr.configure_source("remote", "http://srv:8000/v1", "k", "m")
        mock_build.assert_not_called()
        assert sr.mode == "remote"
        assert sr.remote_base_url == "http://srv:8000/v1"
        assert sr.is_ready is False
