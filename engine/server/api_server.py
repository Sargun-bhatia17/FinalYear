"""
api_server.py — Local IPC Bridge (WebSocket / HTTP)
=====================================================
Runs a lightweight local server on a randomized high port (e.g. :8421).
Streams real-time calculated attention metrics to the Tauri frontend.

Endpoints (planned):
  WS  /stream        — Real-time attention score + state updates
  GET /status        — Current state, risk score, active session info
  GET /sessions      — Historical behavioral_sessions data
  GET /model/status  — ML model training state + W_ml confidence weight
"""

# TODO: Task Sequence 4 — implement WebSocket / HTTP server
