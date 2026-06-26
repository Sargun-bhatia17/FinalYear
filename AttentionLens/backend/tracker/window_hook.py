import os
import sys

# Windows imports setup with fallback
HAS_WIN32 = False
if sys.platform == "win32":
    try:
        import win32gui
        import win32process
        import win32con
        import win32api
        HAS_WIN32 = True
    except ImportError:
        pass

class WindowHook:
    def __init__(self):
        self.last_process = "unknown"
        self.last_title = "unknown"

    def get_active_window(self) -> tuple[str, str]:
        """
        Gets the active window's process name and title.
        Returns:
            Tuple[str, str]: (process_name, window_title)
        """
        if not HAS_WIN32:
            # Fallback mock for non-Windows or environments without pywin32
            return self._get_mock_window()

        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return "Idle", "No active window"
                
            # Get process ID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            # Get window title
            window_title = win32gui.GetWindowText(hwnd)
            
            # Get process name
            process_name = "unknown"
            try:
                handle = win32api.OpenProcess(
                    win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, 
                    False, 
                    pid
                )
                # Get the process image name
                path = win32process.GetModuleFileNameEx(handle)
                process_name = os.path.basename(path)
                win32api.CloseHandle(handle)
            except Exception:
                # If we cannot read the file, default to process name via PID or window class
                try:
                    process_name = win32gui.GetClassName(hwnd)
                except Exception:
                    pass
            
            # Simple clean up of process names
            if not process_name:
                process_name = "unknown"
                
            return process_name, window_title
        except Exception as e:
            # Safe fallback on runtime error
            return "system", f"System Active Window (Error: {e})"

    def _get_mock_window(self) -> tuple[str, str]:
        """Provides simulated active window changes for demo/development purposes."""
        import random
        # Simulate active windows based on time/randomness
        windows = [
            ("code.exe", "activity_repository.py - AttentionLens - Visual Studio Code"),
            ("chrome.exe", "LeetCode - Two Sum - Google Chrome"),
            ("chrome.exe", "Weekly Manga Updates - Chapter 120 - Google Chrome"),
            ("figma.exe", "AttentionLens Dashboard Layout - Figma"),
            ("explorer.exe", "Downloads"),
        ]
        # Return a random window
        return random.choice(windows)
