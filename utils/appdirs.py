"""
Пути данных приложения MDelta Meetings.

Единая точка получения %LOCALAPPDATA%\\MDelta Meetings.
При первом запуске после ребрендинга переносит данные из
старой директории "AI Meetings" (модели, .env, сессии) —
чтобы пользователю не пришлось скачивать модели заново.
"""
import os

APP_NAME = 'MDelta Meetings'
_LEGACY_NAME = 'AI Meetings'


def _base_dir() -> str:
    return os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))


def get_app_dir() -> str:
    """Возвращает директорию данных приложения, создавая её при необходимости.

    Если есть legacy-директория "AI Meetings", а новой ещё нет — пытается
    мигрировать данные простым os.rename (тот же диск). Если rename не удался
    (директория занята другим процессом) — продолжаем работать с legacy-путём,
    миграция повторится при следующем запуске.
    """
    base = _base_dir()
    new_dir = os.path.join(base, APP_NAME)
    legacy_dir = os.path.join(base, _LEGACY_NAME)

    if not os.path.exists(new_dir) and os.path.isdir(legacy_dir):
        try:
            os.rename(legacy_dir, new_dir)
            print(f"[AppDirs] Данные перенесены: {legacy_dir} -> {new_dir}")
        except OSError as e:
            print(f"[AppDirs] Миграция не удалась ({e}), используется {legacy_dir}")
            return legacy_dir

    os.makedirs(new_dir, exist_ok=True)
    return new_dir


def get_models_dir() -> str:
    path = os.path.join(get_app_dir(), 'models')
    os.makedirs(path, exist_ok=True)
    return path
