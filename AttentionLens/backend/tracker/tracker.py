"""
tracker.py
----------
Phase 2: The Silent Observer — Background Tracker

This is the central tracker module for AttentionLens. It integrates:
  - Step 2.1: Active window polling every 1 second using pywin32
  - Step 2.2: Non-blocking pynput keyboard/mouse listeners (count-only, never records characters)
  - Step 2.3: 5-second accumulator loop that flushes counters and writes to the database

PRIVACY GUARANTEE:
    Keyboard listener increments key_count += 1 ONLY.
    The actual key pressed is NEVER stored, logged, or transmitted.
    Mouse listener only records click counts and vertical scroll delta as integers.

Usage:
    # Standalone console mode (prints output, no DB write):
    python -m backend.tracker.tracker

    # Integrated with the DataRepository:
    from backend.tracker.tracker import Tracker
    from backend.repository.repository import DataRepository

    repo = DataRepository()
    tracker = Tracker(repository=repo)
    tracker.start()          # Starts all background threads
    # ... app runs ...
    tracker.stop()           # Graceful shutdown
"""

import os
import sys
import time
import json
import threading
import datetime

# ── pywin32 for OS-level active window detection ──────────────────────────────
try:
    import win32gui
    import win32process
    import win32con
    import win32api
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False
    print("[Tracker] WARNING: pywin32 not installed. Window detection running in mock mode.")

# ── pynput for non-blocking global keyboard/mouse input capture ───────────────
try:
    from pynput import keyboard, mouse
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("[Tracker] WARNING: pynput not installed. Input capture running in simulation mode.")


# ── Configuration loader ──────────────────────────────────────────────────────

def _load_config() -> dict:
    """Loads config.json from the same directory as this file."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ── Step 2.1 — Active Window Inspector ───────────────────────────────────────

class WindowInspector:
    """
    Polls the OS every 1 second to capture the currently active window.

    On Windows: uses pywin32 (win32gui + win32process)
    Fallback:   cycles through mock windows for development/testing

    The inspector runs in its own daemon thread and exposes get_current()
    as a thread-safe snapshot of the latest window state.
    """

    POLL_INTERVAL = 1.0   # seconds between each window check

    def __init__(self, config: dict = None):
        self._config = config or {}
        self._lock = threading.Lock()
        self._current = {"process": "unknown.exe", "title": "Initializing..."}
        self._thread = None
        self._running = False

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="WindowInspector"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def get_current(self) -> dict:
        """Thread-safe read of the latest active window snapshot."""
        with self._lock:
            return dict(self._current)

    # ── Polling loop ──────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """Runs every POLL_INTERVAL seconds, updates internal state."""
        while self._running:
            process_name, window_title = self._get_active_window()
            with self._lock:
                self._current = {
                    "process": process_name,
                    "title":   window_title
                }
            time.sleep(self.POLL_INTERVAL)

    def _get_active_window(self) -> tuple[str, str]:
        """
        Returns (process_name, window_title) for the currently active window.

        Step 2.1 core implementation: uses pywin32 on Windows.
        Falls back to mock data if pywin32 is unavailable.
        """
        if not PYWIN32_AVAILABLE:
            return self._get_mock_window()

        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return "idle", "No active window"

            # Get window title
            window_title = win32gui.GetWindowText(hwnd)

            # Get process name from PID
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                handle = win32api.OpenProcess(
                    win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                    False,
                    pid
                )
                exe_path = win32process.GetModuleFileNameEx(handle, 0)
                win32api.CloseHandle(handle)
                process_name = os.path.basename(exe_path).lower()
            except Exception:
                # Fallback: use window class name if process access is denied
                process_name = win32gui.GetClassName(hwnd).lower() or "unknown.exe"

            return process_name or "unknown.exe", window_title or "Untitled"

        except Exception as e:
            return "system", f"Error reading window: {e}"

    # ── Config-aware keyword check ────────────────────────────────────────────

    def check_keywords(self, window_title: str) -> str | None:
        """
        Checks window title against config.json keyword lists.

        Returns:
            The matched category name ("Core_Tool", "Supporting_Tool", "Leisure")
            or None if no keyword matches.
        """
        title_lower = window_title.lower()
        categories = self._config.get("categories", {})

        for category_name, rules in categories.items():
            for kw in rules.get("title_keywords", []):
                if kw in title_lower:
                    return category_name
        return None

    def _get_mock_window(self) -> tuple[str, str]:
        """Returns rotating mock windows for dev/test environments."""
        import random
        mock_windows = [
            ("code.exe",    "tracker.py — AttentionLens — Visual Studio Code"),
            ("chrome.exe",  "LeetCode — Two Sum — Google Chrome"),
            ("chrome.exe",  "Stack Overflow — python threading — Google Chrome"),
            ("figma.exe",   "Dashboard Design — Figma"),
            ("chrome.exe",  "YouTube — Lofi Hip Hop — Google Chrome"),
        ]
        return random.choice(mock_windows)


# ── Step 2.2 — Non-blocking Input Listener ───────────────────────────────────

class InputCounter:
    """
    Non-blocking global keyboard and mouse listener using pynput.

    CRITICAL PRIVACY RULE:
        The _on_key_press callback receives a `key` argument from pynput.
        This argument is INTENTIONALLY IGNORED.
        Only the integer counter is incremented: key_count += 1
        No character data is ever accessed, stored, or transmitted.

    Thread-safe counters:
        key_count   : total keystrokes since last flush
        click_count : total mouse button presses since last flush
        scroll_y    : cumulative vertical scroll delta since last flush
    """

    SCROLL_MULTIPLIER = 120   # Windows WHEEL_DELTA convention

    def __init__(self):
        self._lock = threading.Lock()

        # ── COUNTER DECLARATIONS ──────────────────────────────────────────────
        # These are the ONLY values ever stored. No key names, no characters.
        self.key_count   : int = 0    # incremented on each key press
        self.click_count : int = 0    # incremented on each mouse button press
        self.scroll_y    : int = 0    # signed cumulative scroll delta
        # ─────────────────────────────────────────────────────────────────────

        self._kb_listener    = None
        self._mouse_listener = None
        self._sim_thread     = None
        self._running        = False

    def start(self) -> None:
        """Starts non-blocking pynput listeners in background threads."""
        self._running = True

        if PYNPUT_AVAILABLE:
            # Keyboard listener
            # NOTE: The `key` parameter in on_press is NEVER read — only the
            # counter is incremented. This is the privacy-critical design.
            self._kb_listener = keyboard.Listener(
                on_press=self._on_key_press
            )
            self._kb_listener.start()

            # Mouse listener
            self._mouse_listener = mouse.Listener(
                on_click=self._on_click,
                on_scroll=self._on_scroll
            )
            self._mouse_listener.start()
        else:
            # Simulation fallback for environments without pynput
            self._sim_thread = threading.Thread(
                target=self._simulate_inputs,
                daemon=True,
                name="InputSimulator"
            )
            self._sim_thread.start()

    def stop(self) -> None:
        self._running = False
        if self._kb_listener:
            self._kb_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()

    # ── Step 2.2 Core: Count-only callbacks ───────────────────────────────────

    def _on_key_press(self, key) -> None:
        """
        Fires on every key press event.
        `key` argument is received but INTENTIONALLY NEVER USED.
        Only the counter is incremented.
        """
        with self._lock:
            self.key_count += 1        # <-- ONLY increment. No key data stored.

    def _on_click(self, x, y, button, pressed: bool) -> None:
        """
        Fires on mouse button events. Only presses (not releases) are counted.
        x, y, button are INTENTIONALLY IGNORED.
        """
        if pressed:
            with self._lock:
                self.click_count += 1  # <-- ONLY increment. No position stored.

    def _on_scroll(self, x, y, dx, dy) -> None:
        """
        Fires on scroll wheel events.
        Only the vertical component (dy) is accumulated.
        x, y, dx are INTENTIONALLY IGNORED.
        """
        with self._lock:
            self.scroll_y += int(dy * self.SCROLL_MULTIPLIER)

    # ── Flush ─────────────────────────────────────────────────────────────────

    def flush(self) -> dict:
        """
        Atomically reads counter values and resets them to zero.
        Called every 5 seconds by the accumulator loop.

        Returns:
            {"keys": int, "clicks": int, "scrolls": int}
        """
        with self._lock:
            snapshot = {
                "keys":    self.key_count,
                "clicks":  self.click_count,
                "scrolls": self.scroll_y
            }
            # ── RESET ALL COUNTERS ────────────────────────────────────────────
            self.key_count   = 0
            self.click_count = 0
            self.scroll_y    = 0
        return snapshot

    def _simulate_inputs(self) -> None:
        """Generates synthetic inputs when pynput is unavailable."""
        import random
        while self._running:
            time.sleep(1.0)
            with self._lock:
                if random.random() < 0.70:
                    self.key_count   += random.randint(1, 10)
                if random.random() < 0.30:
                    self.click_count += random.randint(1, 2)
                if random.random() < 0.20:
                    self.scroll_y    += random.choice([-1, 1]) * self.SCROLL_MULTIPLIER * random.randint(1, 3)


# ── Step 2.3 — 5-Second Accumulator Loop ─────────────────────────────────────

class Tracker:
    """
    The Silent Observer — top-level coordinator.

    Brings together WindowInspector and InputCounter, then runs the
    5-second accumulator loop:

        Every 5 seconds:
            1. Read active window snapshot from WindowInspector
            2. Flush counters from InputCounter
            3. Print combined dict to console
            4. (If repository provided) call repository.insert_raw_event()
            5. Repeat

    The repository integration is optional — pass repository=None to run
    in console-only mode for development and verification.
    """

    FLUSH_INTERVAL = 5   # seconds between each DB write / console print

    def __init__(self, repository=None, config: dict = None):
        """
        Args:
            repository: A DataRepository instance. If None, runs in console-only mode.
            config:     The loaded config.json dict. Auto-loads if not provided.
        """
        self._config     = config or _load_config()
        self._repository = repository
        self._window     = WindowInspector(config=self._config)
        self._inputs     = InputCounter()
        self._thread     = None
        self._running    = False

    def start(self) -> None:
        """Starts the window inspector, input listeners, and accumulator loop."""
        print("[Tracker] Starting AttentionLens Silent Observer...")
        self._window.start()
        self._inputs.start()

        self._running = True
        self._thread  = threading.Thread(
            target=self._accumulator_loop,
            daemon=True,
            name="AccumulatorLoop"
        )
        self._thread.start()
        print("[Tracker] All components running. Flushing every 5 seconds.")

    def stop(self) -> None:
        """Gracefully stops all threads."""
        self._running = False
        self._window.stop()
        self._inputs.stop()
        print("[Tracker] Stopped.")

    # ── Step 2.3 Core: Accumulator Loop ──────────────────────────────────────

    def _accumulator_loop(self) -> None:
        """
        Runs indefinitely on a background daemon thread.

        Every FLUSH_INTERVAL seconds:
          - Grabs the most-recently-observed active window
          - Flushes and resets all input counters atomically
          - Builds the combined event dictionary
          - Prints to console for verification
          - Writes to the database via repository.insert_raw_event()
        """
        while self._running:
            # Wait for the flush interval
            time.sleep(self.FLUSH_INTERVAL)

            # Step 2.3a — Read the latest window snapshot
            window = self._window.get_current()

            # Step 2.3b — Flush and reset input counters
            inputs = self._inputs.flush()

            # Step 2.3c — Build combined event dict (exactly as specified)
            event = {
                "process": window["process"],
                "title":   window["title"],
                "keys":    inputs["keys"],
                "clicks":  inputs["clicks"],
                "scrolls": inputs["scrolls"],
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            # Step 2.3d — Print to console for verification
            print(event)

            # Step 2.3e — Write to database if repository is connected
            if self._repository is not None:
                try:
                    self._repository.insert_raw_event(
                        process=event["process"],
                        title=event["title"],
                        keys=event["keys"],
                        clicks=event["clicks"],
                        scroll=event["scrolls"]
                    )
                except Exception as e:
                    print(f"[Tracker] DB write error: {e}")


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Standalone console mode.
    Run with: python -m backend.tracker.tracker
              OR: python backend/tracker/tracker.py

    Prints a combined event dict every 5 seconds without writing to the DB.
    Press Ctrl+C to stop.
    """
    print("=" * 60)
    print("  AttentionLens — Phase 2 Tracker (Console Mode)")
    print("  Press Ctrl+C to stop")
    print("=" * 60)

    # Console-only mode: no repository passed
    tracker = Tracker(repository=None)
    tracker.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tracker.stop()
        print("\n[Tracker] Stopped by user.")
