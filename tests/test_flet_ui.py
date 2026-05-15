import pytest
import flet as ft
from unittest.mock import MagicMock, patch
from src.flet_ui import FletAudioAssistantUI

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
