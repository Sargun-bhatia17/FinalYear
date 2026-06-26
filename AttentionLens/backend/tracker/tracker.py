"""
tracker.py
----------
Phase 2: The Silent Observer — production-grade background tracker.

Integrates:
  - Step 2.1: Active window polling (configurable interval, default 1s) via pywin32
  - Step 2.2: Non-blocking pynput listeners — count-only, never records key content
  - Step 2.3: Accumulator loop — dominant-window attribution, DB flush, optional callback

PRIVACY GUARANTEE:
    Keyboard listener increments key_count += 1 ONLY.
    The actual key pressed is NEVER stored, logged, or transmitted.
    Mouse listener only records click counts and vertical scroll delta as integers.
    Window titles ARE stored (required for classification) — truncated to 512 chars only.

Production mode (default):
    Requires pywin32 and pynput. Fails fast if hooks cannot attach.

Dev/simulation mode (ATTENTIONLENS_DEV=1):
    Uses mock windows and synthetic input when OS hooks are unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import random
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Deque, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.repository.repository import DataRepository

logger = logging.getLogger(__name__)

# ── Optional OS hooks ─────────────────────────────────────────────────────────

try:
    import win32api
    import win32con
    import win32gui
    import win32process
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

try:
    from pynput import keyboard, mouse
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

_DEV_MODE_DEFAULT = os.environ.get("ATTENTIONLENS_DEV", "").strip().lower() in ("1", "true", "yes")
MAX_TITLE_LENGTH = 512
MAX_RETRY_QUEUE = 12
JOIN_TIMEOUT_SEC = 3.0


# ── Configuration & data types ────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class TrackerConfig:
    """Runtime configuration loaded from config.json tracking section."""

    poll_interval_seconds: float = 1.0
    flush_interval_seconds: float = 5.0
    session_interval_seconds: float = 60.0
    idle_threshold_seconds: float = 180.0
    max_title_length: int = MAX_TITLE_LENGTH

    @classmethod
    def from_dict(cls, raw: dict) -> TrackerConfig:
        tracking = raw.get("tracking", {})
        return cls(
            poll_interval_seconds=float(tracking.get("poll_interval_seconds", 1.0)),
            flush_interval_seconds=float(tracking.get("flush_interval_seconds", 5.0)),
            session_interval_seconds=float(tracking.get("session_interval_seconds", 60.0)),
            idle_threshold_seconds=float(tracking.get("idle_threshold_seconds", 180.0)),
        )


@dataclass(frozen=True, slots=True)
class RawEventSnapshot:
    """Typed 5-second flush payload passed to callbacks and the repository."""

    process: str
    title: str
    keys: int
    clicks: int
    scrolls: int
    timestamp: str
    is_idle: bool = False


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def normalize_process_name(name: str) -> str:
    """Standardize process names to lowercase basename."""
    if not name:
        return "unknown.exe"
    return os.path.basename(name).lower()


def sanitize_title(title: str, max_length: int = MAX_TITLE_LENGTH) -> str:
    """Truncate window title; preserve content needed for classification."""
    if not title or not title.strip():
        return "Untitled"
    cleaned = title.strip()
    if len(cleaned) > max_length:
        return cleaned[:max_length]
    return cleaned


def select_dominant_window(samples: list[dict]) -> dict:
    """
    Pick the dominant process over a flush window (mode of 1s samples).
    Returns {"process", "title", "is_idle"}.
    """
    if not samples:
        return {"process": "unknown.exe", "title": "No samples", "is_idle": False}

    idle_markers = {"idle", "__idle__", "no active window"}

    def _is_idle_sample(sample: dict) -> bool:
        proc = sample.get("process", "").lower()
        title = sample.get("title", "").strip().lower()
        return proc in idle_markers or title in idle_markers or not title

    if all(_is_idle_sample(s) for s in samples):
        return {"process": "__idle__", "title": "Away from desk", "is_idle": True}

    process_counts = Counter(s["process"] for s in samples)
    dominant_process = process_counts.most_common(1)[0][0]
    title = next(
        (s["title"] for s in reversed(samples) if s["process"] == dominant_process),
        "Untitled",
    )
    return {"process": dominant_process, "title": title, "is_idle": False}


# ── Step 2.1 — Active Window Inspector ───────────────────────────────────────

class WindowInspector:
    """
    Polls the OS at poll_interval_seconds and maintains a rolling sample buffer
    for dominant-window attribution over each flush interval.
    """

    def __init__(
        self,
        config: dict | None = None,
        tracker_config: TrackerConfig | None = None,
        dev_mode: bool = False,
    ):
        self._config = config or {}
        self._tracker_config = tracker_config or TrackerConfig.from_dict(self._config)
        self._dev_mode = dev_mode
        self._lock = threading.Lock()
        self._current = {"process": "unknown.exe", "title": "Initializing..."}
        max_samples = max(1, int(self._tracker_config.flush_interval_seconds))
        self._samples: Deque[dict] = deque(maxlen=max_samples)
        self._thread: threading.Thread | None = None
        self._running = False
        self._ok = False

    @property
    def ok(self) -> bool:
        return self._ok

    def start(self) -> None:
        if not PYWIN32_AVAILABLE and not self._dev_mode:
            raise RuntimeError(
                "pywin32 is required for window tracking. "
                "Set ATTENTIONLENS_DEV=1 for simulation mode."
            )
        self._running = True
        self._ok = PYWIN32_AVAILABLE or self._dev_mode
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="WindowInspector",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=JOIN_TIMEOUT_SEC)

    def get_current(self) -> dict:
        with self._lock:
            return dict(self._current)

    def get_dominant_window(self) -> dict:
        with self._lock:
            return select_dominant_window(list(self._samples))

    def clear_samples(self) -> None:
        with self._lock:
            self._samples.clear()

    def check_keywords(self, window_title: str) -> str | None:
        title_lower = window_title.lower()
        categories = self._config.get("categories", {})
        for category_name, rules in categories.items():
            for kw in rules.get("title_keywords", []):
                if kw in title_lower:
                    return category_name
        return None

    def _poll_loop(self) -> None:
        interval = self._tracker_config.poll_interval_seconds
        while self._running:
            process_name, window_title = self._get_active_window()
            process_name = normalize_process_name(process_name)
            window_title = sanitize_title(
                window_title, self._tracker_config.max_title_length
            )
            sample = {"process": process_name, "title": window_title}
            with self._lock:
                self._current = sample
                self._samples.append(sample)
            time.sleep(interval)

    def _get_active_window(self) -> tuple[str, str]:
        if not PYWIN32_AVAILABLE:
            return self._get_mock_window()

        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return "idle", "No active window"

            window_title = win32gui.GetWindowText(hwnd)
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                handle = win32api.OpenProcess(
                    win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                    False,
                    pid,
                )
                exe_path = win32process.GetModuleFileNameEx(handle, 0)
                win32api.CloseHandle(handle)
                process_name = os.path.basename(exe_path)
            except OSError:
                process_name = win32gui.GetClassName(hwnd) or "unknown.exe"

            return process_name or "unknown.exe", window_title or "Untitled"
        except OSError as exc:
            logger.warning("Window read error: %s", exc)
            return "system", "Window read error"

    def _get_mock_window(self) -> tuple[str, str]:
        mock_windows = [
            ("code.exe", "tracker.py — AttentionLens — Visual Studio Code"),
            ("chrome.exe", "LeetCode — Two Sum — Google Chrome"),
            ("chrome.exe", "Stack Overflow — python threading — Google Chrome"),
            ("figma.exe", "Dashboard Design — Figma"),
            ("chrome.exe", "YouTube — Lofi Hip Hop — Google Chrome"),
        ]
        return random.choice(mock_windows)


# ── Step 2.2 — Non-blocking Input Listener ───────────────────────────────────

class InputCounter:
    """
    Count-only global input capture via pynput.

    Hot-path callbacks enqueue lightweight tokens; a dedicated aggregator thread
    increments counters so pynput threads never block on locks.
    """

    SCROLL_MULTIPLIER = 120

    _KEY = 0
    _CLICK = 1

    def __init__(self, dev_mode: bool = False):
        self._dev_mode = dev_mode
        self._lock = threading.Lock()
        self._key_count = 0
        self._click_count = 0
        self._scroll_y = 0
        self._event_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._kb_listener = None
        self._mouse_listener = None
        self._agg_thread: threading.Thread | None = None
        self._sim_thread: threading.Thread | None = None
        self._running = False
        self._ok = False

    @property
    def ok(self) -> bool:
        return self._ok

    def start(self) -> None:
        if not PYNPUT_AVAILABLE and not self._dev_mode:
            raise RuntimeError(
                "pynput is required for input tracking. "
                "Set ATTENTIONLENS_DEV=1 for simulation mode."
            )

        self._running = True
        self._agg_thread = threading.Thread(
            target=self._aggregate_loop,
            daemon=True,
            name="InputAggregator",
        )
        self._agg_thread.start()

        if PYNPUT_AVAILABLE:
            self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
            self._mouse_listener = mouse.Listener(
                on_click=self._on_click,
                on_scroll=self._on_scroll,
            )
            self._kb_listener.start()
            self._mouse_listener.start()
            self._ok = True
            logger.info("InputCounter started — pynput listeners active.")
        else:
            self._sim_thread = threading.Thread(
                target=self._simulate_inputs,
                daemon=True,
                name="InputSimulator",
            )
            self._sim_thread.start()
            self._ok = True
            logger.warning("InputCounter started in SIMULATION mode.")

    def stop(self) -> None:
        self._running = False
        if self._kb_listener:
            self._kb_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._agg_thread and self._agg_thread.is_alive():
            self._agg_thread.join(timeout=JOIN_TIMEOUT_SEC)

    def peek(self) -> dict[str, int]:
        with self._lock:
            return {
                "keys": self._key_count,
                "clicks": self._click_count,
                "scrolls": self._scroll_y,
            }

    def flush(self) -> dict[str, int]:
        self._drain_queue()
        with self._lock:
            snapshot = {
                "keys": self._key_count,
                "clicks": self._click_count,
                "scrolls": self._scroll_y,
            }
            self._key_count = 0
            self._click_count = 0
            self._scroll_y = 0
        return snapshot

    def listeners_alive(self) -> bool:
        if not PYNPUT_AVAILABLE:
            return self._ok
        if self._kb_listener is None and self._mouse_listener is None:
            return self._ok
        kb_ok = self._kb_listener is None or self._kb_listener.running
        mouse_ok = self._mouse_listener is None or self._mouse_listener.running
        return kb_ok and mouse_ok

    def restart_listeners(self) -> bool:
        if not PYNPUT_AVAILABLE:
            return False
        try:
            if self._kb_listener:
                self._kb_listener.stop()
            if self._mouse_listener:
                self._mouse_listener.stop()
            self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
            self._mouse_listener = mouse.Listener(
                on_click=self._on_click,
                on_scroll=self._on_scroll,
            )
            self._kb_listener.start()
            self._mouse_listener.start()
            logger.info("InputCounter listeners restarted.")
            return True
        except Exception as exc:
            logger.error("Failed to restart input listeners: %s", exc)
            return False

    def _on_key_press(self, key: Any) -> None:
        # PRIVACY: `key` is intentionally never read, logged, or stored.
        try:
            self._event_queue.put_nowait(self._KEY)
        except queue.Full:
            pass

    def _on_click(self, x: int | float, y: int | float, button: Any, pressed: bool) -> None:
        if pressed:
            try:
                self._event_queue.put_nowait(self._CLICK)
            except queue.Full:
                pass

    def _on_scroll(self, x: int | float, y: int | float, dx: int | float, dy: int | float) -> None:
        try:
            self._event_queue.put_nowait(("scroll", int(dy * self.SCROLL_MULTIPLIER)))
        except queue.Full:
            pass

    def _aggregate_loop(self) -> None:
        while self._running:
            self._drain_queue(max_batch=500)
            time.sleep(0.05)

    def _drain_queue(self, max_batch: int = 10_000) -> None:
        batch_keys = 0
        batch_clicks = 0
        batch_scroll = 0
        for _ in range(max_batch):
            try:
                item = self._event_queue.get_nowait()
            except queue.Empty:
                break
            if item == self._KEY:
                batch_keys += 1
            elif item == self._CLICK:
                batch_clicks += 1
            elif isinstance(item, tuple) and item[0] == "scroll":
                batch_scroll += item[1]

        if batch_keys or batch_clicks or batch_scroll:
            with self._lock:
                self._key_count += batch_keys
                self._click_count += batch_clicks
                self._scroll_y += batch_scroll

    def _simulate_inputs(self) -> None:
        while self._running:
            time.sleep(1.0)
            with self._lock:
                if random.random() < 0.70:
                    self._key_count += random.randint(1, 10)
                if random.random() < 0.30:
                    self._click_count += random.randint(1, 2)
                if random.random() < 0.20:
                    self._scroll_y += (
                        random.choice([-1, 1])
                        * self.SCROLL_MULTIPLIER
                        * random.randint(1, 3)
                    )


# ── Step 2.3 — Accumulator / Orchestrator ────────────────────────────────────

class Tracker:
    """
    Top-level Silent Observer coordinator.

    Every flush_interval_seconds:
      1. Dominant window from 1s sample buffer
      2. Flush input counters
      3. Write to repository (with retry queue on failure)
      4. Invoke optional on_flush callback
    """
    _raw_config: dict
    _tracker_config: TrackerConfig
    _dev_mode: bool
    _repository: Optional[DataRepository]
    _on_flush: Optional[Callable[[RawEventSnapshot], None]]
    _window: WindowInspector
    _inputs: InputCounter
    _thread: Optional[threading.Thread]
    _running: bool
    _retry_queue: Deque[RawEventSnapshot]
    _lock: threading.Lock
    _events_written: int
    _flush_count: int
    _last_flush_at: Optional[str]
    _last_error: Optional[str]
    _mode: str

    def __init__(
        self,
        repository: Optional[DataRepository] = None,
        config: dict | None = None,
        tracker_config: TrackerConfig | None = None,
        on_flush: Callable[[RawEventSnapshot], None] | None = None,
        dev_mode: bool | None = None,
    ):
        self._raw_config = config or _load_config()
        self._tracker_config = tracker_config or TrackerConfig.from_dict(self._raw_config)
        self._dev_mode = _DEV_MODE_DEFAULT if dev_mode is None else dev_mode
        self._repository = repository
        self._on_flush = on_flush
        self._window = WindowInspector(
            config=self._raw_config,
            tracker_config=self._tracker_config,
            dev_mode=self._dev_mode,
        )
        self._inputs = InputCounter(dev_mode=self._dev_mode)
        self._thread: threading.Thread | None = None
        self._running = False
        self._retry_queue: Deque[RawEventSnapshot] = deque(maxlen=MAX_RETRY_QUEUE)
        self._lock = threading.Lock()
        self._events_written = 0
        self._flush_count = 0
        self._last_flush_at: str | None = None
        self._last_error: str | None = None
        self._mode = (
            "simulation"
            if self._dev_mode or not (PYWIN32_AVAILABLE and PYNPUT_AVAILABLE)
            else "live"
        )

    def start(self) -> None:
        mode_label = "simulation" if self._dev_mode else "live"
        logger.info(
            "Starting Silent Observer (%s mode, flush every %ss)...",
            mode_label,
            self._tracker_config.flush_interval_seconds,
        )
        self._window.start()
        self._inputs.start()
        self._running = True
        self._thread = threading.Thread(
            target=self._accumulator_loop,
            daemon=False,
            name="AccumulatorLoop",
        )
        self._thread.start()
        logger.info("Silent Observer running.")

    def stop(self) -> None:
        logger.info("Stopping Silent Observer...")
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=JOIN_TIMEOUT_SEC)
        self._perform_flush(final=True)
        self._window.stop()
        self._inputs.stop()
        logger.info("Silent Observer stopped.")

    def health(self) -> dict:
        with self._lock:
            return {
                "mode": self._mode,
                "window_ok": self._window.ok,
                "input_ok": self._inputs.ok and self._inputs.listeners_alive(),
                "last_flush_at": self._last_flush_at,
                "flush_count": self._flush_count,
                "events_written": self._events_written,
                "retry_queue_size": len(self._retry_queue),
                "last_error": self._last_error,
            }

    @property
    def flush_interval(self) -> float:
        return self._tracker_config.flush_interval_seconds

    @property
    def session_interval(self) -> float:
        return self._tracker_config.session_interval_seconds

    def _accumulator_loop(self) -> None:
        interval = self._tracker_config.flush_interval_seconds
        next_flush = time.monotonic() + interval
        health_check_counter = 0

        while self._running:
            now = time.monotonic()
            sleep_for = max(0.05, next_flush - now)
            time.sleep(sleep_for)

            if not self._running:
                break

            self._perform_flush()
            next_flush += interval

            health_check_counter += 1
            if health_check_counter >= 12 and not self._inputs.listeners_alive():
                logger.warning("Input listeners died — attempting restart.")
                self._inputs.restart_listeners()
                health_check_counter = 0

    def _perform_flush(self, final: bool = False) -> None:
        window = self._window.get_dominant_window()
        inputs = self._inputs.flush()
        self._window.clear_samples()

        snapshot = RawEventSnapshot(
            process=normalize_process_name(window["process"]),
            title=sanitize_title(
                window["title"], self._tracker_config.max_title_length
            ),
            keys=inputs["keys"],
            clicks=inputs["clicks"],
            scrolls=inputs["scrolls"],
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            is_idle=window.get("is_idle", False),
        )

        if snapshot.is_idle:
            snapshot = RawEventSnapshot(
                process="__idle__",
                title=snapshot.title,
                keys=0,
                clicks=0,
                scrolls=0,
                timestamp=snapshot.timestamp,
                is_idle=True,
            )

        logger.debug(
            "Flush process=%s keys=%d clicks=%d scrolls=%d%s",
            snapshot.process,
            snapshot.keys,
            snapshot.clicks,
            snapshot.scrolls,
            " (final)" if final else "",
        )

        self._flush_retry_queue()
        if self._repository is not None:
            self._persist_snapshot(snapshot)

        if self._on_flush:
            try:
                self._on_flush(snapshot)
            except Exception as exc:
                logger.error("on_flush callback error: %s", exc)

        with self._lock:
            self._flush_count += 1
            self._last_flush_at = snapshot.timestamp

    def _persist_snapshot(self, snapshot: RawEventSnapshot) -> None:
        try:
            self._repository.insert_raw_event(
                process=snapshot.process,
                title=snapshot.title,
                keys=snapshot.keys,
                clicks=snapshot.clicks,
                scroll=snapshot.scrolls,
            )
            with self._lock:
                self._events_written += 1
                self._last_error = None
        except Exception as exc:
            logger.error("DB write error: %s", exc)
            with self._lock:
                self._last_error = str(exc)
                if len(self._retry_queue) < MAX_RETRY_QUEUE:
                    self._retry_queue.append(snapshot)

    def _flush_retry_queue(self) -> None:
        if not self._repository or not self._retry_queue:
            return
        pending: Deque[RawEventSnapshot] = deque()
        with self._lock:
            while self._retry_queue:
                pending.append(self._retry_queue.popleft())

        for snapshot in pending:
            try:
                self._repository.insert_raw_event(
                    process=snapshot.process,
                    title=snapshot.title,
                    keys=snapshot.keys,
                    clicks=snapshot.clicks,
                    scroll=snapshot.scrolls,
                )
                with self._lock:
                    self._events_written += 1
                    self._last_error = None
                logger.info("Retry queue: persisted event for %s", snapshot.process)
            except Exception as exc:
                logger.error("Retry queue write failed: %s", exc)
                with self._lock:
                    self._last_error = str(exc)
                    if len(self._retry_queue) < MAX_RETRY_QUEUE:
                        self._retry_queue.append(snapshot)
                break


# Backward-compatible alias
InputListener = InputCounter


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    dev = _DEV_MODE_DEFAULT
    if not dev and (not PYWIN32_AVAILABLE or not PYNPUT_AVAILABLE):
        logger.error(
            "Production mode requires pywin32 and pynput. "
            "Set ATTENTIONLENS_DEV=1 for simulation."
        )
        raise SystemExit(1)

    tracker = Tracker(repository=None, dev_mode=dev)
    tracker.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tracker.stop()
