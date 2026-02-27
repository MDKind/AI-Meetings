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
    Клиент для OpenAI API и совместимых сервисов (LM Studio, Ollama и др.)

    Поддерживает два режима:
    - OpenAI SDK  — стандартный /v1/chat/completions  (OpenAI, Ollama, старые LM Studio)
    - LM Studio Runtime API — /api/v1/chat  (новые версии LM Studio)
    """
    MAX_HISTORY_MESSAGES = 50

    def __init__(self, api_key=None, model=CHATGPT_SETTINGS['default_model'],
                 max_tokens=CHATGPT_SETTINGS['max_tokens'],
                 base_url=None):

        if base_url is None:
            base_url = CHATGPT_SETTINGS.get('api_base_url') or None
        if base_url == '':
            base_url = None

        if api_key is None:
            api_key = CHATGPT_SETTINGS.get('api_key') or os.getenv("OPENAI_API_KEY")
        if not api_key:
            if base_url:
                api_key = "local"
            else:
                raise ValueError(
                    "Необходимо указать OPENAI_API_KEY (для OpenAI) "
                    "или OPENAI_API_BASE (для LM Studio / Ollama) в файле .env."
                )

        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.conversation_history = []
        self.system_prompt = CHATGPT_SETTINGS['system_prompt']

        self._lmstudio_runtime = _is_lmstudio_runtime(base_url)

        if not self._lmstudio_runtime:
            from openai import OpenAI
            client_kwargs = {'api_key': api_key}
            if base_url:
                client_kwargs['base_url'] = base_url
            self.client = OpenAI(**client_kwargs)
        else:
            self.client = None  # не используется в режиме LM Studio Runtime

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

        # LM Studio Runtime возвращает {"response": "...", "model": "...", ...}
        if 'response' in data:
            return data['response']
        if 'choices' in data and data['choices']:
            return data['choices'][0].get('message', {}).get('content', '') or ''
        if 'content' in data:
            return data['content']
        raise RuntimeError(f"Неожиданный формат ответа LM Studio: {list(data.keys())}")

    def _send(self, messages, max_tokens=None):
        """Универсальный метод отправки — выбирает нужный транспорт."""
        if max_tokens is None:
            max_tokens = self.max_tokens
        if self._lmstudio_runtime:
            return self._chat_lmstudio(messages, max_tokens)
        return self._chat_openai(messages, max_tokens)

    # ── Публичные методы ───────────────────────────────────────────────────────

    def add_message(self, content, role="user", speaker="unknown"):
        """
        speaker: "local" (mic), "remote" (system audio), "unknown"
        Поле хранится в истории, но не отправляется в LLM.
        """
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "speaker": speaker,
        })
        while len(self.conversation_history) > self.MAX_HISTORY_MESSAGES:
            self.conversation_history.pop(0)

    def get_response(self, prompt=None):
        if prompt:
            self.add_message(prompt)
        try:
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(
                {"role": m["role"], "content": m["content"]}
                for m in self.conversation_history
            )
            response_text = self._send(messages)
            self.add_message(response_text, role="assistant")
            return response_text
        except Exception as e:
            print(f"Ошибка при получении ответа: {e}")
            return f"Ошибка: {str(e)}"

    def generate_meeting_summary(self):
        summary_prompt = """
        Пожалуйста, создайте краткое саммари этой встречи, включающее:
        1. Основные обсуждаемые темы
        2. Ключевые решения и выводы
        3. Вопросы, которые остались открытыми
        4. Следующие шаги и назначенные задачи

        Формат: структурированное резюме в виде маркированных списков.
        """
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(
            {"role": m["role"], "content": m["content"]}
            for m in self.conversation_history
        )
        messages.append({"role": "user", "content": summary_prompt})
        try:
            return self._send(messages, max_tokens=2000)
        except Exception as e:
            print(f"Ошибка при генерации саммари: {e}")
            return f"Ошибка при создании саммари: {str(e)}"

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
