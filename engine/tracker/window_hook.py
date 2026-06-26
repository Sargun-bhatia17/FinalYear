"""
window_hook.py — OS Window Activity Poller
===========================================
Queries the currently active window every 1 second using:
  - pywin32  (Windows)
  - AppKit   (macOS)

Returns: process_name, window_title
Accumulates data; flushes to DB via repository every 5 seconds.
"""

# TODO: Task Sequence 1 — implement OS-specific window polling
