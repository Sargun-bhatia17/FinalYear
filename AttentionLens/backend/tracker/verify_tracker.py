"""Phase 2 verification — runs 12s in dev mode, asserts flush count and health."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import time
from backend.tracker.tracker import Tracker

flush_events: list = []


def on_flush(snapshot):
    flush_events.append(snapshot)
    assert snapshot.keys >= 0
    assert snapshot.clicks >= 0
    assert snapshot.process
    assert snapshot.title


tracker = Tracker(repository=None, dev_mode=True, on_flush=on_flush)
tracker.start()

time.sleep(12)
health = tracker.health()
tracker.stop()

assert health["flush_count"] >= 2, f"Expected >=2 flushes, got {health['flush_count']}"
assert len(flush_events) >= 2, f"Expected >=2 callback events, got {len(flush_events)}"
assert health["window_ok"] is True
assert health["input_ok"] is True

print(f"[verify_tracker] Done — {health['flush_count']} flushes, {len(flush_events)} callbacks.")
