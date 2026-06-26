"""Unit tests for Phase 2 tracker — no OS hooks required."""

import inspect

import pytest

from backend.tracker.tracker import (
    InputCounter,
    RawEventSnapshot,
    normalize_process_name,
    sanitize_title,
    select_dominant_window,
)


class TestDominantWindow:
    def test_empty_samples(self):
        result = select_dominant_window([])
        assert result["process"] == "unknown.exe"

    def test_mode_process_wins(self):
        samples = [
            {"process": "code.exe", "title": "a.py - VS Code"},
            {"process": "code.exe", "title": "a.py - VS Code"},
            {"process": "chrome.exe", "title": "YouTube"},
            {"process": "code.exe", "title": "b.py - VS Code"},
        ]
        result = select_dominant_window(samples)
        assert result["process"] == "code.exe"
        assert result["title"] == "b.py - VS Code"
        assert result["is_idle"] is False

    def test_all_idle(self):
        samples = [
            {"process": "idle", "title": "No active window"},
            {"process": "idle", "title": ""},
        ]
        result = select_dominant_window(samples)
        assert result["process"] == "__idle__"
        assert result["is_idle"] is True


class TestSanitization:
    def test_normalize_process_name(self):
        assert normalize_process_name("C:\\Apps\\Code.EXE") == "code.exe"
        assert normalize_process_name("") == "unknown.exe"

    def test_sanitize_title_truncates(self):
        long_title = "x" * 600
        assert len(sanitize_title(long_title)) == 512

    def test_sanitize_empty_title(self):
        assert sanitize_title("") == "Untitled"


class TestInputCounter:
    def test_flush_resets_counters(self):
        counter = InputCounter(dev_mode=True)
        counter.start()
        with counter._lock:
            counter._key_count = 5
            counter._click_count = 2
            counter._scroll_y = 120
        snap = counter.flush()
        assert snap == {"keys": 5, "clicks": 2, "scrolls": 120}
        assert counter.peek() == {"keys": 0, "clicks": 0, "scrolls": 0}
        counter.stop()

    def test_key_press_callback_ignores_key_argument(self):
        source = inspect.getsource(InputCounter._on_key_press)
        assert "key_count" in source or "_event_queue" in source
        assert "str(key)" not in source
        assert "key.char" not in source
        assert "log" not in source.lower() or "intentionally" in source.lower()


class TestRawEventSnapshot:
    def test_frozen_dataclass(self):
        snap = RawEventSnapshot(
            process="code.exe",
            title="test",
            keys=1,
            clicks=0,
            scrolls=0,
            timestamp="2026-01-01 00:00:00",
        )
        assert snap.process == "code.exe"
