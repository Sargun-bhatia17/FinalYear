"""
feature_engineer.py — ML Feature Vector Builder
=================================================
Aggregates raw session data into a 5-dimensional feature array
every 60 seconds for Random Forest inference:

  f0 : Mean Interaction Density (I_D) over last 5 minutes
  f1 : Mean Scroll Velocity (S_V) over last 5 minutes
  f2 : Context Switching Entropy (E_C)
  f3 : Core Tool Presence Ratio  (0.0 → 1.0)
  f4 : Time-of-Day Float Index   (e.g. 14.5 = 2:30 PM)
"""

# TODO: Task Sequence 2 — implement feature extraction pipeline
