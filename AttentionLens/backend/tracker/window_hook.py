"""
window_hook.py — legacy compatibility shim.

Prefer ``WindowInspector`` from ``backend.tracker.tracker``.
"""

from backend.tracker.tracker import WindowInspector, normalize_process_name, sanitize_title


class WindowHook:
    """Thin wrapper around WindowInspector for backward compatibility."""

    def __init__(self, dev_mode: bool = True):
        self._inspector = WindowInspector(dev_mode=dev_mode)

    def get_active_window(self) -> tuple[str, str]:
        if not self._inspector._samples and not self._inspector._current.get("process"):
            proc, title = self._inspector._get_active_window()
        else:
            snap = self._inspector.get_current()
            proc, title = snap["process"], snap["title"]
        return normalize_process_name(proc), sanitize_title(title)
