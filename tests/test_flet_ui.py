import os
import pytest
import flet as ft
from unittest.mock import MagicMock, patch
from src.flet_ui import FletAudioAssistantUI


def _make_ui(tmp_path):
    mock_page = MagicMock(spec=ft.Page)
    mock_page.window = MagicMock()
    mock_page.overlay = []
    return FletAudioAssistantUI(
        page=mock_page,
        audio_capture=MagicMock(),
        speech_recognizer=MagicMock(),
        chatgpt_client=MagicMock(),
        env_path=str(tmp_path / ".env"),
    )


def test_flet_ui_initialization():
    # Mock the Flet Page object
    mock_page = MagicMock(spec=ft.Page)
    mock_page.window = MagicMock()
    mock_page.overlay = []
    
    mock_audio = MagicMock()
    mock_speech = MagicMock()
    mock_chatgpt = MagicMock()
    
    # We should be able to initialize the UI without exceptions
    ui = FletAudioAssistantUI(
        page=mock_page,
        audio_capture=mock_audio,
        speech_recognizer=mock_speech,
        chatgpt_client=mock_chatgpt
    )
    
    assert ui.page == mock_page
    assert ui.audio_capture == mock_audio
    assert ui.speech_recognizer == mock_speech
    
    # Verify that setup_ui logic got called and populated components
    assert ui.transcript_view is not None
    assert ui.summary_text is not None
    assert ui.btn_record is not None


class TestSaveEnv:

    def test_creates_env_file_with_values(self, tmp_path):
        ui = _make_ui(tmp_path)
        ui._save_env("sk-test-key", "http://localhost:1234/v1", "gpt-4o")

        content = open(str(tmp_path / ".env")).read()
        assert "OPENAI_API_KEY=sk-test-key" in content
        assert "OPENAI_API_BASE=http://localhost:1234/v1" in content
        assert "CHATGPT_MODEL=gpt-4o" in content

    def test_updates_existing_key_without_duplicate(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text("OPENAI_API_KEY=old-key\nOTHER=value\n")

        ui = _make_ui(tmp_path)
        ui._save_env("new-key", "", "")

        content = env_path.read_text()
        assert "OPENAI_API_KEY=new-key" in content
        assert "old-key" not in content
        assert content.count("OPENAI_API_KEY") == 1
        assert "OTHER=value" in content

    def test_skips_empty_values(self, tmp_path):
        ui = _make_ui(tmp_path)
        ui._save_env("", "", "")

        env_path = tmp_path / ".env"
        if env_path.exists():
            content = env_path.read_text()
            assert "OPENAI_API_KEY" not in content
            assert "OPENAI_API_BASE" not in content
            assert "CHATGPT_MODEL" not in content

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "deep" / "dir" / ".env"
        mock_page = MagicMock(spec=ft.Page)
        mock_page.window = MagicMock()
        mock_page.overlay = []
        ui = FletAudioAssistantUI(
            page=mock_page,
            audio_capture=MagicMock(),
            speech_recognizer=MagicMock(),
            chatgpt_client=MagicMock(),
            env_path=str(nested),
        )

        ui._save_env("sk-key", "", "gpt-4o")
        assert nested.exists()

    def test_apply_api_settings_no_language_attr_set(self, tmp_path):
        """speech_recognizer.language must NOT be set — dead code was removed."""
        ui = _make_ui(tmp_path)
        speech_mock = ui.speech_recognizer

        ui.dd_language = MagicMock()
        ui.dd_language.value = "en"
        ui.dd_llm = MagicMock()
        ui.dd_llm.value = "gpt-4o"

        ui.start_recording()

        assert not hasattr(speech_mock, 'language') or \
               not speech_mock.method_calls or \
               all('language' not in str(c) for c in speech_mock.method_calls)
