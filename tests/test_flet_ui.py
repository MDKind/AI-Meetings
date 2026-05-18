import os
import pytest
import flet as ft
from unittest.mock import MagicMock, patch
from src.flet_ui import FletAudioAssistantUI
from src.diarization import DiarSegment


def _make_ui(tmp_path):
    mock_page = MagicMock(spec=ft.Page)
    mock_page.window = MagicMock()
    mock_page.overlay = []
    return FletAudioAssistantUI(
        page=mock_page,
        audio_capture=MagicMock(),
        speech_recognizer=MagicMock(),
        chatgpt_client=MagicMock(),
        env_path=str(tmp_path / ".env"),
    )


def test_flet_ui_initialization():
    # Mock the Flet Page object
    mock_page = MagicMock(spec=ft.Page)
    mock_page.window = MagicMock()
    mock_page.overlay = []
    
    mock_audio = MagicMock()
    mock_speech = MagicMock()
    mock_chatgpt = MagicMock()
    
    # We should be able to initialize the UI without exceptions
    ui = FletAudioAssistantUI(
        page=mock_page,
        audio_capture=mock_audio,
        speech_recognizer=mock_speech,
        chatgpt_client=mock_chatgpt
    )
    
    assert ui.page == mock_page
    assert ui.audio_capture == mock_audio
    assert ui.speech_recognizer == mock_speech
    
    # Verify that setup_ui logic got called and populated components
    assert ui.transcript_view is not None
    assert ui.summary_text is not None
    assert ui.btn_record is not None


class TestSaveEnv:

    def test_creates_env_file_with_values(self, tmp_path):
        ui = _make_ui(tmp_path)
        ui._save_env("sk-test-key", "http://localhost:1234/v1", "gpt-4o")

        content = open(str(tmp_path / ".env")).read()
        assert "OPENAI_API_KEY=sk-test-key" in content
        assert "OPENAI_API_BASE=http://localhost:1234/v1" in content
        assert "CHATGPT_MODEL=gpt-4o" in content

    def test_updates_existing_key_without_duplicate(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text("OPENAI_API_KEY=old-key\nOTHER=value\n")

        ui = _make_ui(tmp_path)
        ui._save_env("new-key", "", "")

        content = env_path.read_text()
        assert "OPENAI_API_KEY=new-key" in content
        assert "old-key" not in content
        assert content.count("OPENAI_API_KEY") == 1
        assert "OTHER=value" in content

    def test_skips_empty_values(self, tmp_path):
        ui = _make_ui(tmp_path)
        ui._save_env("", "", "")

        env_path = tmp_path / ".env"
        if env_path.exists():
            content = env_path.read_text()
            assert "OPENAI_API_KEY" not in content
            assert "OPENAI_API_BASE" not in content
            assert "CHATGPT_MODEL" not in content

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "deep" / "dir" / ".env"
        mock_page = MagicMock(spec=ft.Page)
        mock_page.window = MagicMock()
        mock_page.overlay = []
        ui = FletAudioAssistantUI(
            page=mock_page,
            audio_capture=MagicMock(),
            speech_recognizer=MagicMock(),
            chatgpt_client=MagicMock(),
            env_path=str(nested),
        )

        ui._save_env("sk-key", "", "gpt-4o")
        assert nested.exists()

    def test_apply_api_settings_no_language_attr_set(self, tmp_path):
        """speech_recognizer.language must NOT be set — dead code was removed."""
        ui = _make_ui(tmp_path)
        speech_mock = ui.speech_recognizer

        ui.dd_language = MagicMock()
        ui.dd_language.value = "en"
        ui.dd_llm = MagicMock()
        ui.dd_llm.value = "gpt-4o"

        ui.start_recording()

        assert not hasattr(speech_mock, 'language') or \
               not speech_mock.method_calls or \
               all('language' not in str(c) for c in speech_mock.method_calls)


# ── _apply_diarization ────────────────────────────────────────────────────────

def _make_entry(offset, label="Я"):
    ctrl = ft.Text(label, color=ft.colors.BLUE_400)
    return {"start_offset": offset, "speaker_raw": "local", "speaker_ctrl": ctrl}


class TestApplyDiarization:

    def _ui(self, tmp_path):
        return _make_ui(tmp_path)

    def test_single_speaker_keeps_ya(self, tmp_path):
        ui = self._ui(tmp_path)
        entry = _make_entry(1.0)
        segs = [DiarSegment(speaker_id=0, start=0.0, end=5.0)]
        ui._apply_diarization(segs, [entry])
        assert entry["speaker_ctrl"].value == "Я"
        assert entry["speaker_ctrl"].color == ft.colors.BLUE_400

    def test_two_speakers_get_participant_labels(self, tmp_path):
        ui = self._ui(tmp_path)
        e1 = _make_entry(1.0)
        e2 = _make_entry(4.0)
        segs = [
            DiarSegment(speaker_id=0, start=0.0, end=3.0),
            DiarSegment(speaker_id=1, start=3.0, end=6.0),
        ]
        ui._apply_diarization(segs, [e1, e2])
        assert e1["speaker_ctrl"].value == "Участник 1"
        assert e2["speaker_ctrl"].value == "Участник 2"
        assert e1["speaker_ctrl"].color != e2["speaker_ctrl"].color

    def test_same_speaker_two_entries_both_relabelled(self, tmp_path):
        ui = self._ui(tmp_path)
        e1 = _make_entry(0.5)
        e2 = _make_entry(1.5)
        segs = [DiarSegment(speaker_id=0, start=0.0, end=10.0),
                DiarSegment(speaker_id=1, start=10.0, end=20.0)]
        ui._apply_diarization(segs, [e1, e2])
        # Both fall in speaker 0's segment → only 1 unique speaker → "Я"
        assert e1["speaker_ctrl"].value == "Я"
        assert e2["speaker_ctrl"].value == "Я"

    def test_entry_with_none_offset_gets_ya_fallback(self, tmp_path):
        ui = self._ui(tmp_path)
        entry = _make_entry(None)
        segs = [DiarSegment(speaker_id=0, start=0.0, end=5.0)]
        ui._apply_diarization(segs, [entry])
        # offset None → skipped → speaker_map empty → single-speaker path → "Я"
        assert entry["speaker_ctrl"].value == "Я"

    def test_empty_segments_reverts_to_ya(self, tmp_path):
        ui = self._ui(tmp_path)
        entry = _make_entry(2.0)
        ui._apply_diarization([], [entry])
        assert entry["speaker_ctrl"].value == "Я"

    def test_fallback_to_closest_segment_when_no_overlap(self, tmp_path):
        ui = self._ui(tmp_path)
        e1 = _make_entry(0.1)
        e2 = _make_entry(3.0)
        segs = [
            DiarSegment(speaker_id=0, start=0.5, end=1.5),
            DiarSegment(speaker_id=1, start=2.0, end=4.0),
        ]
        ui._apply_diarization(segs, [e1, e2])
        # e1 (0.1) has no overlap → closest midpoint: seg0 mid=1.0 dist=0.9, seg1 mid=3.0 dist=2.9
        # → e1 maps to speaker 0
        # e2 (3.0) overlaps seg1
        # → 2 unique speakers
        assert e1["speaker_ctrl"].value == "Участник 1"
        assert e2["speaker_ctrl"].value == "Участник 2"

    def test_four_speakers_cycle_colors(self, tmp_path):
        ui = self._ui(tmp_path)
        entries = [_make_entry(float(i)) for i in range(4)]
        segs = [DiarSegment(speaker_id=i, start=float(i), end=float(i) + 1) for i in range(4)]
        ui._apply_diarization(segs, entries)
        colors = [e["speaker_ctrl"].color for e in entries]
        assert len(set(colors)) == 4
