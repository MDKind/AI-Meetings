"""Тесты utils/appdirs.py — директория данных и миграция из legacy "AI Meetings"."""
import os


def test_creates_new_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from utils.appdirs import get_app_dir
    result = get_app_dir()
    assert result == str(tmp_path / "MDelta Meetings")
    assert os.path.isdir(result)


def test_migrates_legacy_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = tmp_path / "AI Meetings"
    (legacy / "models").mkdir(parents=True)
    (legacy / ".env").write_text("WHISPER_MODEL=base\n")

    from utils.appdirs import get_app_dir
    result = get_app_dir()

    assert result == str(tmp_path / "MDelta Meetings")
    assert not legacy.exists()
    assert (tmp_path / "MDelta Meetings" / ".env").read_text() == "WHISPER_MODEL=base\n"
    assert (tmp_path / "MDelta Meetings" / "models").is_dir()


def test_existing_new_dir_wins_over_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    (tmp_path / "MDelta Meetings").mkdir()
    (tmp_path / "AI Meetings").mkdir()
    (tmp_path / "AI Meetings" / "old.txt").write_text("x")

    from utils.appdirs import get_app_dir
    result = get_app_dir()

    assert result == str(tmp_path / "MDelta Meetings")
    # legacy не тронута — обе существуют, миграция не нужна
    assert (tmp_path / "AI Meetings" / "old.txt").exists()


def test_get_models_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from utils.appdirs import get_models_dir
    result = get_models_dir()
    assert result == str(tmp_path / "MDelta Meetings" / "models")
    assert os.path.isdir(result)
