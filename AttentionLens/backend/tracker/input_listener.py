"""
input_listener.py
-----------------
Developer B — Activity Capture Engine

Captures keyboard and mouse activity using non-blocking pynput listeners.

PRIVACY GUARANTEE:
    - Keyboard listener ONLY increments a counter. It NEVER records which
      key was pressed, no character data is stored or logged.
    - Mouse listener records click count and vertical scroll delta only.
    - No personally identifiable data is captured at any point.

Usage:
    listener = InputListener()
    listener.start()

    # Later, to read and reset the counters atomically:
    snapshot = listener.flush()
    print(snapshot)  # {"keys": 14, "clicks": 3, "scrolls": 120}

    listener.stop()
"""

import threading
from typing import Dict

try:
    from pynput import keyboard, mouse
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("[InputListener] WARNING: pynput not installed. Running in simulation mode.")


class InputListener:
    """
    Non-blocking input capture using pynput.

    Maintains three thread-safe counters:
      - _key_count    : total keystrokes detected
      - _click_count  : total mouse button presses detected
      - _scroll_delta : cumulative vertical scroll distance (pixels equivalent)

    Characters pressed are NEVER stored — only the count is incremented.
    """

    # Scroll multiplier: pynput dy is typically ±1 or ±3 per notch.
    # Multiply by 120 to match Windows WHEEL_DELTA convention (120 per notch).
    SCROLL_MULTIPLIER = 120

    def __init__(self):
        self._lock = threading.Lock()

        # Counters — all protected by _lock
        self._key_count: int = 0
        self._click_count: int = 0
        self._scroll_delta: int = 0

        self._kb_listener = None
        self._mouse_listener = None
        self._running = False

        # Simulation thread for environments without pynput
        self._sim_thread = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Starts the non-blocking keyboard and mouse listeners."""
        if self._running:
            return

        self._running = True

        if PYNPUT_AVAILABLE:
            # Keyboard: on_press fires on every key press.
            # We ONLY increment the count — the `key` argument is ignored.
            self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
            self._kb_listener.start()

            # Mouse: on_click fires for button presses and releases.
            # We only count presses (pressed=True).
            self._mouse_listener = mouse.Listener(
                on_click=self._on_click,
                on_scroll=self._on_scroll
            )
            self._mouse_listener.start()

            print("[InputListener] Started — pynput keyboard & mouse listeners active.")
        else:
            # Simulation mode: generates realistic-looking fake inputs.
            self._sim_thread = threading.Thread(
                target=self._simulate_inputs,
                daemon=True,
                name="InputSimulator"
            )
            self._sim_thread.start()
            print("[InputListener] Started — running in SIMULATION mode (pynput unavailable).")

    def stop(self) -> None:
        """Stops all listeners gracefully."""
        self._running = False

        if PYNPUT_AVAILABLE:
            if self._kb_listener:
                self._kb_listener.stop()
            if self._mouse_listener:
                self._mouse_listener.stop()

        print("[InputListener] Stopped.")

    # ── Public API ────────────────────────────────────────────────────────────

    def flush(self) -> Dict[str, int]:
        """
        Atomically reads the current counter values and resets them to zero.
        This is the primary read interface — call it every 5 seconds.

        Returns:
            Dict with keys: "keys", "clicks", "scrolls"
        """
        with self._lock:
            snapshot = {
                "keys":    self._key_count,
                "clicks":  self._click_count,
                "scrolls": self._scroll_delta
            }
            # Reset all counters after reading
            self._key_count    = 0
            self._click_count  = 0
            self._scroll_delta = 0

        return snapshot

    def peek(self) -> Dict[str, int]:
        """
        Reads current counter values WITHOUT resetting them.
        Useful for real-time display without disturbing the accumulation window.

        Returns:
            Dict with keys: "keys", "clicks", "scrolls"
        """
        with self._lock:
            return {
                "keys":    self._key_count,
                "clicks":  self._click_count,
                "scrolls": self._scroll_delta
            }

    # ── pynput Callbacks ──────────────────────────────────────────────────────

    def _on_key_press(self, key) -> None:
        """
        Called by pynput on every key press event.
        The `key` parameter is intentionally ignored — we only count.
        """
        with self._lock:
            self._key_count += 1

    def _on_click(self, x: int, y: int, button, pressed: bool) -> None:
        """
        Called by pynput on every mouse button event.
        We only count actual presses, not releases.
        x, y, button are intentionally ignored.
        """
        if pressed:
            with self._lock:
                self._click_count += 1

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        """
        Called by pynput on every mouse scroll event.
        dy is positive for scroll-up, negative for scroll-down.
        We accumulate the total vertical scroll distance.
        x, y, dx are intentionally ignored.
        """
        with self._lock:
            self._scroll_delta += int(dy * self.SCROLL_MULTIPLIER)

    # ── Simulation Mode ───────────────────────────────────────────────────────

    def _simulate_inputs(self) -> None:
        """
        Generates synthetic keyboard and mouse activity for development/testing.
        Runs when pynput is unavailable. Mimics realistic usage patterns.
        """
        import time
        import random

        while self._running:
            time.sleep(1.0)
            with self._lock:
                # Simulate keystrokes: active typing ~70% of the time
                if random.random() < 0.70:
                    self._key_count += random.randint(1, 10)

                # Simulate mouse clicks: ~30% chance per second
                if random.random() < 0.30:
                    self._click_count += random.randint(1, 2)

                # Simulate scrolling: ~20% chance per second
                if random.random() < 0.20:
                    direction = random.choice([-1, 1])
                    self._scroll_delta += direction * self.SCROLL_MULTIPLIER * random.randint(1, 3)
