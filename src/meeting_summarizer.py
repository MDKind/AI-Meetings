from datetime import datetime


class MeetingSummarizer:
    """
    Генерирует структурированное саммари встречи через LLM.
    Хранение результата — через utils/storage.py.
    """

    def __init__(self, chatgpt_client):
        self.chatgpt_client = chatgpt_client

    def generate_summary(self, title=None):
        """
        Генерирует саммари встречи через LLM.

        Returns:
            dict: {title, date, duration_seconds, summary, transcript}
        """
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

        try:
            raw_summary = self.chatgpt_client.get_response(summary_prompt)

            return {
                "title": title or f"Встреча {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration_seconds": self._calc_duration_seconds(),
                "summary": raw_summary,
                "transcript": self._get_transcript(),
            }

        except Exception as e:
            print(f"Ошибка при генерации саммари: {e}")
            return {
                "title": title or f"Встреча {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration_seconds": 0,
                "error": str(e),
                "transcript": [],
            }

    def _calc_duration_seconds(self):
        """Считает длительность встречи по timestamp'ам в истории."""
        history = self.chatgpt_client.conversation_history
        if len(history) < 2:
            return 0
        try:
            fmt = "%Y-%m-%dT%H:%M:%S.%f"
            t_start = datetime.fromisoformat(history[0]["timestamp"])
            t_end = datetime.fromisoformat(history[-1]["timestamp"])
            return int((t_end - t_start).total_seconds())
        except Exception:
            return 0

    def _get_transcript(self):
        """Возвращает расшифровку из истории разговора."""
        return [
            {
                "role": m["role"],
                "content": m["content"],
                "timestamp": m.get("timestamp", ""),
                "speaker": m.get("speaker", "unknown"),
            }
            for m in self.chatgpt_client.conversation_history
        ]
