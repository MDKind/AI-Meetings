import pytest
from unittest.mock import MagicMock, patch
from src.chatgpt_client import ChatGPTClient

@pytest.fixture
def mock_settings():
    with patch('src.chatgpt_client.CHATGPT_SETTINGS', {
        'default_model': 'gpt-4o',
        'max_tokens': 1000,
        'system_prompt': 'You are a test assistant',
        'api_key': 'test-key',
        'api_base_url': None
    }):
        yield

def test_add_message(mock_settings):
    client = ChatGPTClient()
    client.add_message("Hello", role="user", speaker="local")
    
    assert len(client.conversation_history) == 1
    assert client.conversation_history[0]["role"] == "user"
    assert client.conversation_history[0]["content"] == "Hello"
    assert client.conversation_history[0]["speaker"] == "local"
    assert "timestamp" in client.conversation_history[0]

def test_generate_meeting_summary_contains_plaud_note_prompt(mock_settings):
    client = ChatGPTClient()
    client.add_message("Test message")
    
    # Mock the _send method to just return the prompt it received
    client._send = MagicMock(return_value="Mocked summary")
    
    result = client.generate_meeting_summary()
    
    assert result == "Mocked summary"
    client._send.assert_called_once()
    
    # Verify the prompt sent to _send
    messages_sent = client._send.call_args[0][0]
    # system prompt + history + summary_prompt
    assert len(messages_sent) == 3
    assert messages_sent[0]["role"] == "system"
    assert messages_sent[1]["content"] == "Test message"
    
    summary_prompt = messages_sent[-1]["content"]
    assert "Plaud Note" in summary_prompt
    assert "## 📝 Краткая выжимка (Summary)" in summary_prompt
