"""Тесты MDelta API провайдера в ChatGPTClient (JWT-логин, /api/chat, 401-retry)."""
import pytest
from unittest.mock import MagicMock, patch

from src.chatgpt_client import ChatGPTClient


def _resp(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def _make_client(**kwargs):
    defaults = dict(
        api_key="unused",
        provider="mdelta",
        mdelta_base_url="http://mdelta.local",
        mdelta_username="user1",
        mdelta_password="pass1",
    )
    defaults.update(kwargs)
    return ChatGPTClient(**defaults)


class TestMDeltaLogin:

    def test_login_stores_token(self):
        client = _make_client()
        with patch("src.chatgpt_client.requests.post",
                   return_value=_resp({"accessToken": "jwt-123"})) as mock_post:
            token = client._mdelta_login()

        assert token == "jwt-123"
        assert client._mdelta_token == "jwt-123"
        args, kwargs = mock_post.call_args
        assert args[0] == "http://mdelta.local/api/auth/login"
        assert kwargs["json"] == {"username": "user1", "password": "pass1"}

    def test_login_without_url_raises(self):
        client = _make_client(mdelta_base_url="")
        with pytest.raises(RuntimeError, match="URL MDelta"):
            client._mdelta_login()

    def test_login_without_token_in_response_raises(self):
        client = _make_client()
        with patch("src.chatgpt_client.requests.post", return_value=_resp({"error": "x"})):
            with pytest.raises(RuntimeError, match="accessToken"):
                client._mdelta_login()

    def test_test_connection_returns_true(self):
        client = _make_client()
        with patch("src.chatgpt_client.requests.post",
                   return_value=_resp({"accessToken": "t"})):
            assert client.test_mdelta_connection() is True


class TestMDeltaChat:

    def test_send_routes_to_mdelta(self):
        client = _make_client()
        client._mdelta_token = "jwt-abc"
        with patch("src.chatgpt_client.requests.post",
                   return_value=_resp({"response": "Ответ MDelta"})) as mock_post:
            result = client._send([
                {"role": "system", "content": "Системный промпт"},
                {"role": "user", "content": "Привет"},
            ])

        assert result == "Ответ MDelta"
        args, kwargs = mock_post.call_args
        assert args[0] == "http://mdelta.local/api/chat"
        assert kwargs["headers"] == {"Authorization": "Bearer jwt-abc"}
        # system prompt свёрнут в текст сообщения
        assert "Системный промпт" in kwargs["json"]["message"]
        assert "Привет" in kwargs["json"]["message"]
        assert kwargs["json"]["userId"] == "mdelta-meetings-user1"

    def test_relogin_on_401(self):
        client = _make_client()
        client._mdelta_token = "expired"

        unauthorized = _resp({}, status=401)
        ok = _resp({"response": "готово"})
        login_ok = _resp({"accessToken": "fresh"})

        def route(url, **kwargs):
            if url.endswith("/api/auth/login"):
                return login_ok
            if kwargs.get("headers", {}).get("Authorization") == "Bearer fresh":
                return ok
            return unauthorized

        with patch("src.chatgpt_client.requests.post", side_effect=route):
            result = client._chat_mdelta([{"role": "user", "content": "hi"}], 100)

        assert result == "готово"
        assert client._mdelta_token == "fresh"

    def test_history_flattened_into_dialog(self):
        client = _make_client()
        client._mdelta_token = "t"
        with patch("src.chatgpt_client.requests.post",
                   return_value=_resp({"answer": "ok"})) as mock_post:
            client._chat_mdelta([
                {"role": "user", "content": "раз"},
                {"role": "assistant", "content": "два"},
                {"role": "user", "content": "три"},
            ], 100)
        message = mock_post.call_args.kwargs["json"]["message"]
        assert "User: раз" in message
        assert "Assistant: два" in message
        assert "User: три" in message

    def test_session_id_reused(self):
        client = _make_client()
        client._mdelta_token = "t"
        first = _resp({"response": "a", "chatSessionId": "sess-9"})
        with patch("src.chatgpt_client.requests.post", return_value=first):
            client._chat_mdelta([{"role": "user", "content": "1"}], 100)
        assert client._mdelta_session_id == "sess-9"

        second = _resp({"response": "b"})
        with patch("src.chatgpt_client.requests.post", return_value=second) as mock_post:
            client._chat_mdelta([{"role": "user", "content": "2"}], 100)
        assert mock_post.call_args.kwargs["json"]["chatSessionId"] == "sess-9"

    def test_unexpected_format_raises(self):
        client = _make_client()
        client._mdelta_token = "t"
        with patch("src.chatgpt_client.requests.post", return_value=_resp({"foo": 1})):
            with pytest.raises(RuntimeError, match="Неожиданный формат"):
                client._chat_mdelta([{"role": "user", "content": "x"}], 100)


class TestProviderSwitching:

    def test_mdelta_provider_has_no_openai_client(self):
        client = _make_client()
        assert client.client is None

    def test_inference_provider_by_default(self):
        client = ChatGPTClient(api_key="sk-test")
        assert client.provider == "inference"

    def test_reinit_switches_provider(self):
        # base_url="" — не зависеть от OPENAI_API_BASE в .env разработчика
        client = ChatGPTClient(api_key="sk-test", base_url="")
        client.provider = "mdelta"
        client._mdelta_token = "stale"
        client._reinit_client()
        assert client.client is None
        assert client._mdelta_token is None  # токен сброшен — перелогин при следующем запросе

        client.provider = "inference"
        client._reinit_client()
        assert client.client is not None
