"""
input_listener.py — legacy compatibility shim.

Prefer ``InputCounter`` from ``backend.tracker.tracker``.
"""

from backend.tracker.tracker import InputCounter, InputListener

__all__ = ["InputListener", "InputCounter"]
