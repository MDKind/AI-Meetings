import pytest
import requests
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


class TestReinitClient:
    def test_sets_none_without_api_key(self, mock_settings):
        c = ChatGPTClient(api_key='', base_url=None)
        c.api_key = ''
        c._reinit_client()
        assert c.client is None

    def test_sets_none_for_lmstudio_runtime(self, mock_settings):
        with patch('openai.OpenAI'):
            c = ChatGPTClient(api_key='sk-x', base_url='http://host/api/v1')
        c._reinit_client()
        assert c.client is None
        assert c._lmstudio_runtime is True

    def test_creates_openai_client_with_key(self, mock_settings):
        with patch('openai.OpenAI') as mock_cls:
            c = ChatGPTClient(api_key='', base_url=None)
            c.api_key = 'sk-new'
            c._reinit_client()
            mock_cls.assert_called_once_with(api_key='sk-new')
            assert c.client is mock_cls.return_value

    def test_creates_client_with_base_url(self, mock_settings):
        with patch('openai.OpenAI') as mock_cls:
            c = ChatGPTClient(api_key='', base_url=None)
            c.api_key = 'local'
            c.base_url = 'http://localhost:1234/v1'
            c._reinit_client()
            mock_cls.assert_called_once_with(api_key='local', base_url='http://localhost:1234/v1')


class TestPolishTranscription:
    def _make_client(self, mock_settings):
        c = ChatGPTClient.__new__(ChatGPTClient)
        c.max_tokens = 2000
        c._lmstudio_runtime = False
        c.client = MagicMock()
        c.base_url = None
        return c

    def test_calls_send_and_returns_result(self, mock_settings):
        c = self._make_client(mock_settings)
        c._send = MagicMock(return_value='Исправленный текст.')
        result = c.polish_transcription('исправленный текст')
        assert c._send.called
        assert result == 'Исправленный текст.'

    def test_returns_original_on_send_error(self, mock_settings):
        c = self._make_client(mock_settings)
        c._send = MagicMock(side_effect=RuntimeError("connection error"))
        result = c.polish_transcription('original text')
        assert result == 'original text'

    def test_returns_empty_string_unchanged(self, mock_settings):
        c = self._make_client(mock_settings)
        c._send = MagicMock()
        result = c.polish_transcription('   ')
        c._send.assert_not_called()
        assert result == '   '


class TestFetchAvailableModels:
    def test_fetches_from_local_server_data_list(self, mock_settings):
        with patch('openai.OpenAI'):
            c = ChatGPTClient(api_key='local', base_url='http://localhost:1234/v1')
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'data': [{'id': 'model-a'}, {'id': 'model-b'}]}
        with patch('requests.get', return_value=mock_resp) as mock_get:
            models = c.fetch_available_models()
        assert models == ['model-a', 'model-b']
        mock_get.assert_called_once_with('http://localhost:1234/v1/models', headers={}, timeout=10)

    def test_fetches_from_local_server_plain_list(self, mock_settings):
        with patch('openai.OpenAI'):
            c = ChatGPTClient(api_key='local', base_url='http://localhost:8080/v1')
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{'id': 'llama-3'}, {'id': 'mistral'}]
        with patch('requests.get', return_value=mock_resp):
            models = c.fetch_available_models()
        assert 'llama-3' in models
        assert 'mistral' in models

    def test_returns_empty_list_when_no_client_and_no_base_url(self, mock_settings):
        c = ChatGPTClient(api_key='', base_url=None)
        assert c.client is None
        models = c.fetch_available_models()
        assert models == []

    def test_override_params_used_instead_of_client_attrs(self, mock_settings):
        with patch('openai.OpenAI'):
            c = ChatGPTClient(api_key='key', base_url='http://original/v1')
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'data': [{'id': 'override-model'}]}
        with patch('requests.get', return_value=mock_resp) as mock_get:
            models = c.fetch_available_models(base_url='http://other:9090/v1', api_key='override-key')
        mock_get.assert_called_once_with(
            'http://other:9090/v1/models',
            headers={'Authorization': 'Bearer override-key'},
            timeout=10,
        )
        assert models == ['override-model']
