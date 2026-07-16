"""
utils/storage.py — единый интерфейс хранения транскрипций и саммари.

Текущая реализация: JSON-файлы в %LOCALAPPDATA%\\MDelta Meetings\\sessions\\
Будущая: подключаемая БД (SQLite / PostgreSQL / etc.) —
  достаточно заменить тело StorageBackend не меняя остальной код.

Структура JSON-сессии:
{
  "session_id": "20260226_103045",
  "title": "...",
  "date": "2026-02-26 10:30:45",
  "duration_seconds": 1234,
  "transcript": [
    {
      "role": "user" | "assistant",
      "speaker": "local" | "remote" | "unknown",
      "content": "...",
      "timestamp": "2026-02-26T10:30:45.123456"
    },
    ...
  ],
  "summary": "...",   // null если ещё не сгенерировано
}
"""

import os
import json
from datetime import datetime


def _sessions_dir() -> str:
    from utils.appdirs import get_app_dir
    base = os.path.join(get_app_dir(), 'sessions')
    os.makedirs(base, exist_ok=True)
    return base


class Storage:
    """
    Фасад хранилища.  Все методы работают с единым форматом dict-сессии.
    Для подключения БД — унаследуйтесь и переопределите _write / _read / list_sessions.
    """

    # ── Запись ─────────────────────────────────────────────────────────────────

    def save_transcript(self, transcript: list, title: str = None,
                        session_id: str = None) -> str:
        """
        Сохраняет транскрипцию встречи.

        Args:
            transcript: список dict {role, speaker, content, timestamp}
            title:      название встречи
            session_id: если None — генерируется по текущему времени

        Returns:
            session_id строки (используется для последующего save_summary)
        """
        sid = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        data = self._load_or_new(sid, title)
        data["transcript"] = transcript
        self._write(sid, data)
        return sid

    def save_summary(self, summary_dict: dict, session_id: str = None) -> str:
        """
        Сохраняет / обновляет саммари в существующую сессию или создаёт новую.

        Args:
            summary_dict: dict из MeetingSummarizer.generate_summary()
            session_id:   ID сессии; если None — создаётся новая

        Returns:
            session_id
        """
        sid = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        data = self._load_or_new(
            sid,
            title=summary_dict.get("title"),
            date=summary_dict.get("date"),
            duration_seconds=summary_dict.get("duration_seconds", 0),
        )
        data["summary"] = summary_dict.get("summary", "")
        if summary_dict.get("transcript"):
            data["transcript"] = summary_dict["transcript"]
        self._write(sid, data)
        return sid

    # ── Чтение ─────────────────────────────────────────────────────────────────

    def load_session(self, session_id: str) -> dict | None:
        """Загружает сессию по ID. Возвращает None если не найдена."""
        path = os.path.join(_sessions_dir(), f"{session_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def list_sessions(self) -> list[dict]:
        """
        Возвращает список всех сессий, отсортированных по дате (новые первые).
        Каждая запись: {session_id, title, date, has_summary}
        """
        result = []
        for fname in os.listdir(_sessions_dir()):
            if not fname.endswith('.json'):
                continue
            sid = fname[:-5]
            try:
                with open(os.path.join(_sessions_dir(), fname), 'r', encoding='utf-8') as f:
                    d = json.load(f)
                result.append({
                    "session_id": sid,
                    "title": d.get("title", sid),
                    "date": d.get("date", ""),
                    "duration_seconds": d.get("duration_seconds", 0),
                    "has_summary": bool(d.get("summary")),
                })
            except Exception:
                pass
        result.sort(key=lambda x: x["date"], reverse=True)
        return result

    # ── Внутренние методы (переопределить для БД) ─────────────────────────────

    def _load_or_new(self, session_id: str, title=None,
                     date=None, duration_seconds=0) -> dict:
        existing = self.load_session(session_id)
        if existing:
            return existing
        return {
            "session_id": session_id,
            "title": title or f"Встреча {session_id}",
            "date": date or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": duration_seconds,
            "transcript": [],
            "summary": None,
        }

    def _write(self, session_id: str, data: dict):
        path = os.path.join(_sessions_dir(), f"{session_id}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Storage: сохранено → {path}")


# Глобальный экземпляр (singleton)
storage = Storage()
