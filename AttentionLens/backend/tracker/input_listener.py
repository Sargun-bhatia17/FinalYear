import threading
import time

# Try to import pynput, with fallback to mock
HAS_PYNPUT = False
try:
    from pynput import mouse, keyboard
    HAS_PYNPUT = True
except ImportError:
    pass

class InputListener:
    def __init__(self):
        self.keystroke_count = 0
        self.mouse_click_count = 0
        self.scroll_delta_y = 0
        self.lock = threading.Lock()
        
        self.keyboard_listener = None
        self.mouse_listener = None
        self.running = False

    def start(self):
        self.running = True
        if HAS_PYNPUT:
            # Start keyboard listener
            self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
            self.keyboard_listener.start()
            
            # Start mouse listener
            self.mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll
            )
            self.mouse_listener.start()
        else:
            print("pynput not available, running in input-simulation mode.")
            # Start background simulation thread
            threading.Thread(target=self._simulate_inputs, daemon=True).start()

    def stop(self):
        self.running = False
        if HAS_PYNPUT:
            if self.keyboard_listener:
                self.keyboard_listener.stop()
            if self.mouse_listener:
                self.mouse_listener.stop()

    def get_and_reset_deltas(self) -> tuple[int, int, int]:
        """
        Retrieves the accumulated counts and resets them.
        Returns:
            Tuple[int, int, int]: (keystrokes, clicks, scroll_delta_y)
        """
        with self.lock:
            keystrokes = self.keystroke_count
            clicks = self.mouse_click_count
            scroll = self.scroll_delta_y
            
            # Reset counters
            self.keystroke_count = 0
            self.mouse_click_count = 0
            self.scroll_delta_y = 0
            
            return keystrokes, clicks, scroll

    # pynput callbacks (privacy-safe, count only)
    def _on_key_press(self, key):
        with self.lock:
            self.keystroke_count += 1

    def _on_mouse_click(self, x, y, button, pressed):
        if pressed:
            with self.lock:
                self.mouse_click_count += 1

    def _on_mouse_scroll(self, x, y, dx, dy):
        with self.lock:
            # Accumulate dy. Standard scroll delta is 1 or -1 units; we scale it for SV calculations.
            self.scroll_delta_y += int(dy * 120)

    # Fallback simulation loop
    def _simulate_inputs(self):
        import random
        while self.running:
            # Sleep 1 second, then randomly add some actions
            time.sleep(1.0)
            with self.lock:
                # 70% chance of keyboard inputs, 50% chance of mouse clicks
                if random.random() < 0.7:
                    self.keystroke_count += random.randint(1, 8)
                if random.random() < 0.5:
                    self.mouse_click_count += random.randint(1, 3)
                if random.random() < 0.2:
                    self.scroll_delta_y += random.choice([-120, 120]) * random.randint(1, 3)
