import pytest
from unittest.mock import MagicMock
from src.meeting_summarizer import MeetingSummarizer

def test_generate_summary_structure():
    mock_client = MagicMock()
    # Mock conversation history
    mock_client.conversation_history = [
        {"role": "user", "content": "Hello", "timestamp": "2026-05-15T10:00:00.000", "speaker": "local"},
        {"role": "user", "content": "Hi there", "timestamp": "2026-05-15T10:00:05.000", "speaker": "remote"}
    ]
    # Mock LLM response
    mock_client.get_response.return_value = "## 📝 Краткая выжимка\nThis is a summary."
    
    summarizer = MeetingSummarizer(mock_client)
    result = summarizer.generate_summary(title="Test Meeting")
    
    assert result["title"] == "Test Meeting"
    assert result["duration_seconds"] == 5
    assert result["summary"] == "## 📝 Краткая выжимка\nThis is a summary."
    assert len(result["transcript"]) == 2
    assert result["transcript"][0]["speaker"] == "local"

    # Verify that get_response was called with the correct prompt
    mock_client.get_response.assert_called_once()
    called_prompt = mock_client.get_response.call_args[0][0]
    assert "Plaud Note" in called_prompt
    assert "Mind Map" in called_prompt
