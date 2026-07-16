import os
import json
import requests
from datetime import datetime
from utils.config import CHATGPT_SETTINGS


def _is_lmstudio_runtime(base_url: str) -> bool:
    """Возвращает True если base_url указывает на LM Studio Runtime API (/api/v1)."""
    return base_url is not None and '/api/v1' in base_url


class ChatGPTClient:
    """
    LLM-клиент для обработки и саммаризации.

    Провайдеры (self.provider):
    - 'inference' — OpenAI-совместимый API:
        * OpenAI SDK  — стандартный /v1/chat/completions  (OpenAI, Ollama, vLLM)
        * LM Studio Runtime API — /api/v1/chat  (новые версии LM Studio)
    - 'mdelta' — MDelta API (RAG-платформа): JWT-логин /api/auth/login,
        диалог через /api/chat.
    """
    MAX_HISTORY_MESSAGES = 50
    _msg_counter = 0  # global monotonic ID for conversation history entries

    def __init__(self, api_key=None, model=CHATGPT_SETTINGS['default_model'],
                 max_tokens=CHATGPT_SETTINGS['max_tokens'],
                 base_url=None, provider=None,
                 mdelta_base_url=None, mdelta_username=None, mdelta_password=None):

        if base_url is None:
            base_url = CHATGPT_SETTINGS.get('api_base_url') or None
        if base_url == '':
            base_url = None

        if api_key is None:
            api_key = CHATGPT_SETTINGS.get('api_key') or os.getenv("OPENAI_API_KEY")
        if not api_key:
            api_key = "local" if base_url else ""

        self.provider = provider or CHATGPT_SETTINGS.get('provider', 'inference')
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.conversation_history = []
        self.system_prompt = CHATGPT_SETTINGS['system_prompt']

        # MDelta API
        self.mdelta_base_url = (mdelta_base_url if mdelta_base_url is not None
                                else CHATGPT_SETTINGS.get('mdelta_base_url', ''))
        self.mdelta_username = (mdelta_username if mdelta_username is not None
                                else CHATGPT_SETTINGS.get('mdelta_username', ''))
        self.mdelta_password = (mdelta_password if mdelta_password is not None
                                else CHATGPT_SETTINGS.get('mdelta_password', ''))
        self._mdelta_token = None
        self._mdelta_session_id = None

        self._lmstudio_runtime = _is_lmstudio_runtime(base_url)

        if self.provider != 'mdelta' and not self._lmstudio_runtime and api_key:
            from openai import OpenAI
            client_kwargs = {'api_key': api_key}
            if base_url:
                client_kwargs['base_url'] = base_url
            self.client = OpenAI(**client_kwargs)
        else:
            self.client = None  # MDelta / LM Studio Runtime / API не настроен

    def _reinit_client(self):
        """Пересоздаёт OpenAI client после смены провайдера, api_key или base_url."""
        self._lmstudio_runtime = _is_lmstudio_runtime(self.base_url)
        self._mdelta_token = None  # заставляем перелогиниться при смене настроек
        if self.provider == 'mdelta' or self._lmstudio_runtime:
            self.client = None
            return
        effective_key = self.api_key or ('local' if self.base_url else '')
        if not effective_key:
            self.client = None
            return
        from openai import OpenAI
        kwargs = {'api_key': effective_key}
        if self.base_url:
            kwargs['base_url'] = self.base_url
        self.client = OpenAI(**kwargs)

    # ── MDelta API транспорт ───────────────────────────────────────────────────

    def _mdelta_login(self) -> str:
        """Логин в MDelta API, возвращает accessToken (JWT)."""
        if not self.mdelta_base_url:
            raise RuntimeError("Не указан URL MDelta API")
        url = self.mdelta_base_url.rstrip('/') + '/api/auth/login'
        resp = requests.post(url, json={
            'username': self.mdelta_username,
            'password': self.mdelta_password,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        token = data.get('accessToken') or data.get('access_token') or data.get('token')
        if not token:
            raise RuntimeError(f"MDelta API не вернул accessToken: {list(data.keys())}")
        self._mdelta_token = token
        return token

    def test_mdelta_connection(self) -> bool:
        """Проверка подключения к MDelta API (логин). Бросает исключение при ошибке."""
        self._mdelta_login()
        return True

    @property
    def _mdelta_user_id(self) -> str:
        """Стабильный userId для скоупинга диалога в MDelta.

        MDelta валидирует userId как UUID v4 (validateAnonymousUser.js),
        поэтому детерминированно строим UUID из имени пользователя:
        один и тот же логин → один и тот же userId → история/память сохраняются.
        """
        import hashlib
        import uuid
        seed = f"mdelta-meetings:{self.mdelta_username or 'user'}"
        raw = bytearray(hashlib.sha256(seed.encode('utf-8')).digest()[:16])
        raw[6] = (raw[6] & 0x0F) | 0x40  # версия 4
        raw[8] = (raw[8] & 0x3F) | 0x80  # вариант RFC 4122
        return str(uuid.UUID(bytes=bytes(raw)))

    # MDelta ограничивает message 32 000 символами (MAX_MESSAGE_LENGTH)
    MDELTA_MAX_MESSAGE_CHARS = 30000

    def _chat_mdelta(self, messages, max_tokens):
        """
        Отправляет запрос через MDelta API (POST /api/chat).

        MDelta принимает одно сообщение (message + userId-UUID), поэтому
        system prompt и история диалога сворачиваются в текст запроса.
        При 401 (протухший JWT) — один повторный логин.
        Ответ: {success, response, chatSessionId, ...}.
        """
        system_msg = next((m['content'] for m in messages if m['role'] == 'system'), '')
        history = [m for m in messages if m['role'] != 'system']

        if len(history) == 1:
            text = history[0]['content']
        else:
            parts = []
            for m in history:
                role = "User" if m['role'] == 'user' else "Assistant"
                parts.append(f"{role}: {m['content']}")
            text = "\n\n".join(parts)
        if system_msg:
            text = f"{system_msg}\n\n{text}"

        # Лимит длины: обрезаем НАЧАЛО истории — конец транскрипта важнее
        if len(text) > self.MDELTA_MAX_MESSAGE_CHARS:
            text = "[...начало обрезано из-за лимита длины...]\n" + \
                   text[-self.MDELTA_MAX_MESSAGE_CHARS:]

        if not self._mdelta_token:
            self._mdelta_login()

        url = self.mdelta_base_url.rstrip('/') + '/api/chat'
        payload = {'message': text, 'userId': self._mdelta_user_id}
        if self._mdelta_session_id:
            payload['chatSessionId'] = self._mdelta_session_id

        for attempt in (1, 2):
            resp = requests.post(
                url, json=payload,
                headers={'Authorization': f'Bearer {self._mdelta_token}'},
                timeout=180,
            )
            if resp.status_code == 401 and attempt == 1:
                self._mdelta_login()
                continue
            break
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, dict) and data.get('chatSessionId'):
            self._mdelta_session_id = data['chatSessionId']

        for key in ('response', 'answer', 'message', 'content', 'text', 'output'):
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, str) and value.strip():
                return value.strip()
        if isinstance(data, dict) and data.get('choices'):
            return data['choices'][0].get('message', {}).get('content', '') or ''
        raise RuntimeError(f"Неожиданный формат ответа MDelta API: "
                           f"{list(data.keys()) if isinstance(data, dict) else type(data)}")

    # ── Низкоуровневые методы отправки ────────────────────────────────────────

    def _chat_openai(self, messages, max_tokens):
        """Отправляет запрос через OpenAI SDK."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7
        )
        if not response.choices:
            raise RuntimeError(
                f"Сервер вернул пустой ответ (model='{self.model}', base_url='{self.base_url}')"
            )
        return response.choices[0].message.content or ""

    def _chat_lmstudio(self, messages, max_tokens):
        """
        Отправляет запрос через LM Studio Runtime API (/api/v1/chat).
        Формат: {"model": "...", "system_prompt": "...", "input": "last user message"}
        История передаётся через conversation_history в виде строки в input.
        """
        system_msg = next((m['content'] for m in messages if m['role'] == 'system'), '')
        history = [m for m in messages if m['role'] != 'system']

        # LM Studio Runtime API требует "input" — строку с последним сообщением пользователя.
        # Если в истории несколько сообщений — передаём всю историю как текст в input.
        if len(history) == 1:
            input_text = history[0]['content']
        else:
            # Форматируем историю как диалог
            parts = []
            for m in history:
                role = "User" if m['role'] == 'user' else "Assistant"
                parts.append(f"{role}: {m['content']}")
            input_text = "\n\n".join(parts)

        url = self.base_url.rstrip('/') + '/chat'
        payload = {
            "model": self.model,
            "input": input_text,
            "temperature": 0.7,
        }
        if system_msg:
            payload["system_prompt"] = system_msg

        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        # LM Studio Runtime: output может быть строкой или списком блоков
        # [{'type': 'reasoning', 'content': '...'}, {'type': 'message', 'content': '...'}]
        if 'output' in data:
            output = data['output']
            if isinstance(output, list):
                # Берём только блоки type=message, игнорируем reasoning
                text = ' '.join(
                    b['content'] for b in output
                    if isinstance(b, dict) and b.get('type') == 'message' and b.get('content')
                )
                if not text:
                    # Fallback: берём любой content
                    text = ' '.join(
                        b['content'] for b in output
                        if isinstance(b, dict) and b.get('content')
                    )
            else:
                text = str(output)
            return text.replace('\\n', '\n').strip()
        if 'response' in data:
            return str(data['response']).replace('\\n', '\n').strip()
        if 'choices' in data and data['choices']:
            return data['choices'][0].get('message', {}).get('content', '') or ''
        if 'content' in data:
            return data['content']
        raise RuntimeError(f"Неожиданный формат ответа LM Studio: {list(data.keys())}")

    def _send(self, messages, max_tokens=None):
        """Универсальный метод отправки — выбирает нужный транспорт."""
        if max_tokens is None:
            max_tokens = self.max_tokens
        if self.provider == 'mdelta':
            return self._chat_mdelta(messages, max_tokens)
        if self._lmstudio_runtime:
            return self._chat_lmstudio(messages, max_tokens)
        return self._chat_openai(messages, max_tokens)

    _SPEAKER_LABEL = {"local": "Я", "remote": "Собеседник"}

    def _history_as_messages(self):
        """Конвертирует conversation_history в список messages для LLM.
        Для сообщений с известным спикером добавляет префикс '[Я]: ' / '[Собеседник]: ',
        чтобы LLM понимал кто что говорил при генерации саммари и ответов.
        """
        result = []
        for m in self.conversation_history:
            content = m["content"]
            speaker = m.get("speaker", "unknown")
            if speaker in self._SPEAKER_LABEL:
                content = f"[{self._SPEAKER_LABEL[speaker]}]: {content}"
            result.append({"role": m["role"], "content": content})
        return result

    # ── Публичные методы ───────────────────────────────────────────────────────

    def add_message(self, content, role="user", speaker="unknown"):
        """
        speaker: "local" (mic), "remote" (system audio), "unknown"
        Returns the unique _id assigned to this message.
        """
        ChatGPTClient._msg_counter += 1
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "speaker": speaker,
            "_id": ChatGPTClient._msg_counter,
        })
        while len(self.conversation_history) > self.MAX_HISTORY_MESSAGES:
            self.conversation_history.pop(0)
        return ChatGPTClient._msg_counter

    def get_response(self, prompt=None):
        if prompt:
            self.add_message(prompt)
        try:
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(self._history_as_messages())
            response_text = self._send(messages)
            self.add_message(response_text, role="assistant")
            return response_text
        except Exception as e:
            print(f"Ошибка при получении ответа: {e}")
            return f"Ошибка: {str(e)}"

    def generate_meeting_summary(self):
        summary_prompt = """
        Вы - профессиональный AI-ассистент для встреч (как Plaud Note). Проанализируйте транскрипт разговора и создайте подробный отчет в формате Markdown.

        Структура отчета должна строго соответствовать следующим разделам:

        ## 📝 Краткая выжимка (Summary)
        (2-3 абзаца с основным смыслом разговора)

        ## 🎯 Ключевые темы и решения (Key Topics & Decisions)
        - (маркированный список основных обсужденных тем и принятых решений)
        
        ## ✅ Задачи (Action Items)
        - [ ] Задачи с указанием ответственных, если они понятны из контекста
        
        ## 🧠 Интеллект-карта (Mind Map)
        (Представьте структуру разговора в виде вложенных списков для удобного чтения)
        """
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self._history_as_messages())
        messages.append({"role": "user", "content": summary_prompt})
        try:
            return self._send(messages, max_tokens=2000)
        except Exception as e:
            print(f"Ошибка при генерации саммари: {e}")
            return f"Ошибка при создании саммари: {str(e)}"

    def polish_transcription(self, text: str) -> str:
        """Улучшает сырой транскрипт через LLM: исправляет ошибки распознавания, пунктуацию, связность."""
        if not text.strip():
            return text
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты редактор транскрипций речи. Твоя задача — исправить ошибки автоматического распознавания: "
                    "неправильно распознанные слова, пропущенные знаки препинания, грамматические ошибки, "
                    "сделать текст связным и читабельным. Сохраняй смысл и стиль речи. "
                    "Верни только исправленный текст без пояснений и без кавычек."
                ),
            },
            {"role": "user", "content": text},
        ]
        try:
            return self._send(messages, max_tokens=min(len(text) * 2 + 100, 1000))
        except Exception as e:
            print(f"[ChatGPT] Ошибка улучшения транскрипта: {e}")
            return text

    def correct_text(self, text: str, instruction: str) -> str:
        """Apply a custom user instruction to a text segment (e.g. fix specific terms)."""
        if not text.strip():
            return text
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты редактор текста. Применяй данную инструкцию к тексту. "
                    "Верни только исправленный текст без пояснений и без кавычек."
                ),
            },
            {
                "role": "user",
                "content": f"Инструкция: {instruction}\n\nТекст: {text}",
            },
        ]
        try:
            return self._send(messages, max_tokens=min(len(text) * 3 + 200, 1000))
        except Exception as e:
            print(f"[ChatGPT] Ошибка правки текста: {e}")
            return text

    def fetch_available_models(self, base_url=None, api_key=None) -> list:
        """Получает список доступных моделей с сервера."""
        _base_url = base_url if base_url is not None else self.base_url
        _api_key = api_key if api_key is not None else self.api_key

        if not _base_url:
            if not self.client:
                return []
            response = self.client.models.list()
            return sorted(m.id for m in response.data)

        url = _base_url.rstrip('/') + '/models'
        headers = {}
        if _api_key and _api_key not in ('', 'local'):
            headers['Authorization'] = f'Bearer {_api_key}'
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get('data', [])
        return [m.get('id', str(m)) if isinstance(m, dict) else str(m) for m in items]

    def save_conversation(self, filename=None):
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.conversation_history, f, ensure_ascii=False, indent=2)
        return filename

    def load_conversation(self, filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                self.conversation_history = json.load(f)
            return True
        except (FileNotFoundError, json.JSONDecodeError):
            return False

    def clear_conversation(self):
        self.conversation_history = []
