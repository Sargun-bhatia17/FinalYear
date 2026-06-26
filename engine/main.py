"""
AttentionLens — Python Sidecar Entry Point
==========================================
Starts all background threads:
  - Window activity tracker (OS hooks)
  - Input listener (pynput)
  - Behavior + rule engine loop (every 60s)
  - Retraining daemon (every 100 sessions / 7 days)
  - Local IPC server (WebSocket / HTTP)
"""

# TODO: Task Sequence 1 — initialize and start all threads
