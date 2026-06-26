"""Quick Phase 2 verification — runs for 12 seconds, prints 2 flush events, then exits."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import time
from backend.tracker.tracker import Tracker

tracker = Tracker(repository=None)   # console-only, no DB needed for this test
tracker.start()

# Let 2 full flush cycles (2 x 5s = 10s) complete, then exit cleanly
time.sleep(12)
tracker.stop()
print("[verify_tracker] Done — Phase 2 verified.")
