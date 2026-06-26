"""
behavior_engine.py — Multi-Parameter Behavioral Math
======================================================
Computes per-60-second scoring vectors:

  Parameter A — Interaction Density (I_D):
    I_D = keystroke_count + mouse_click_count

  Parameter B — Scroll Velocity (S_V):
    S_V = |scroll_delta_y| / interval_duration_seconds

  Parameter C — Context Switching Entropy (E_C):
    E_C = -sum(p_i * log2(p_i))  over rolling 5-min window

  Parameter D — Category Distance (C_D):
    Core→Supporting: 0.1 | Core→Core: 0.0 | Core→Leisure: 1.0
"""

# TODO: Task Sequence 2 — implement all four parameter calculators
