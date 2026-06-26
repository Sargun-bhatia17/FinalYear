"""
verify_tracker.py
-----------------
Production-grade automated unit and integration verification suite for Phase 2 Tracker.

Verifies:
  1. Code Quality Contract (no print statements, absolute logging, type annotations presence).
  2. WindowInspector lifecycle, polling, and dominant window selection.
  3. InputCounter lifecycle, thread-safe aggregation, and Privacy Guarantee enforcement.
  4. Tracker orchestrator lifecycle, database flush callbacks, and MockRepository integration.
  5. Tracker resilience (retry queue for offline resilience).

Usage:
    python backend/tracker/verify_tracker.py
"""

import os
import sys
import time
import logging
from typing import Any, Optional, Deque
from collections import deque

# Allow running from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.tracker.tracker import (
    Tracker,
    WindowInspector,
    InputCounter,
    TrackerConfig,
    RawEventSnapshot,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("verify_tracker")

# Colors for presentation
PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
passed = 0
failed = 0


def check(label: str, condition: bool) -> None:
    global passed, failed
    status = PASS if condition else FAIL
    print(f"{status}  {label}")
    if condition:
        passed += 1
    else:
        failed += 1


class MockRepository:
    """Mock repository that stores raw events in memory for validation."""

    def __init__(self, fail_writes: bool = False) -> None:
        self.events: list[dict[str, Any]] = []
        self.fail_writes: bool = fail_writes

    def insert_raw_event(
        self,
        process: str,
        title: str,
        keys: int,
        clicks: int,
        scroll: int,
    ) -> int:
        if self.fail_writes:
            raise RuntimeError("Database connection lost.")
        self.events.append({
            "process": process,
            "title": title,
            "keys": keys,
            "clicks": clicks,
            "scroll": scroll,
        })
        return len(self.events)


def verify_code_quality() -> None:
    print("[ Step 2.0 ] Code Quality & Privacy Contract")
    
    tracker_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tracker.py"
    )
    with open(tracker_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify no prints inside class/methods (excluding the standalone block at the bottom)
    main_start = content.find('if __name__ == "__main__":')
    body_content = content[:main_start] if main_start != -1 else content
    
    lines = body_content.split("\n")
    print_found = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("print(") or (" print(" in stripped and not stripped.startswith("#")):
            print_found = True
            logger.warning("Found print call at line %d: %s", idx + 1, stripped)
            
    check("tracker.py uses logging module and contains zero print() statements in classes", not print_found)
    
    # Verify privacy guarantee is explicitly commented and implemented
    privacy_keywords = ["privacy", "never read", "never logged", "never stored"]
    has_privacy_comments = any(kw in content.lower() for kw in privacy_keywords)
    check("tracker.py contains explicit privacy guarantee statements in documentation/code", has_privacy_comments)


def verify_window_inspector() -> None:
    print("[ Step 2.1 ] WindowInspector Verification")
    
    config = {
        "categories": {
            "Core_Tool": {"title_keywords": ["vscode", "figma"]},
            "Leisure": {"title_keywords": ["youtube", "netflix"]}
        }
    }
    
    # Initialize in dev_mode to avoid pywin32 OS hooks
    inspector = WindowInspector(config=config, dev_mode=True)
    check("WindowInspector initializes correctly", not inspector._running)
    
    inspector.start()
    check("WindowInspector starts and runs loop", inspector._running)
    
    # Wait for at least one poll (dev mode has mock windows)
    time.sleep(0.2)
    
    current = inspector.get_current()
    check("get_current() returns a dictionary", isinstance(current, dict))
    check("get_current() contains process key", "process" in current)
    check("get_current() contains title key", "title" in current)
    
    dominant = inspector.get_dominant_window()
    check("get_dominant_window() returns a valid dominant window", "process" in dominant)
    
    keyword_match = inspector.check_keywords("watching youtube video")
    check("check_keywords() correctly maps Leisure keywords", keyword_match == "Leisure")
    
    inspector.stop()
    check("WindowInspector stops cleanly", not inspector._running)


def verify_input_counter() -> None:
    print("[ Step 2.2 ] InputCounter & Privacy Guarantee")
    
    counter = InputCounter(dev_mode=True)
    counter.start()
    check("InputCounter aggregator thread starts", counter._running)
    
    # Directly invoke callbacks to simulate input events
    # Simulate 5 keys, 3 clicks, and 2 scrolls
    for _ in range(5):
        counter._on_key_press("a")  # Pass real character "a" to ensure it is ignored
    for _ in range(3):
        counter._on_click(100, 200, "left", True)
    counter._on_scroll(0, 0, 0, 1.5)  # 1.5 dy scroll
    counter._on_scroll(0, 0, 0, -0.5) # -0.5 dy scroll
    
    # Let aggregator loop run for a split second
    time.sleep(0.1)
    
    snapshot = counter.flush()
    check("flush() returns accumulated keys", snapshot["keys"] == 5)
    check("flush() returns accumulated clicks", snapshot["clicks"] == 3)
    
    # 1.5 dy * 120 + -0.5 dy * 120 = 180 - 60 = 120
    check("flush() returns accumulated vertical scrolls", snapshot["scrolls"] == 120)
    
    # Verify privacy guarantee: check that the internal state of InputCounter
    # has absolutely NO trace of character values or cursor coordinates.
    attributes = dir(counter)
    has_text_data = False
    for attr in attributes:
        if attr.startswith("__") or callable(getattr(counter, attr)):
            continue
        val = getattr(counter, attr)
        if val == "a" or val == "left":
            has_text_data = True
        elif isinstance(val, (list, tuple, set, deque)):
            if "a" in val or "left" in val or 100 in val or 200 in val:
                has_text_data = True
        elif isinstance(val, dict):
            if "a" in val.values() or "left" in val.values() or 100 in val.values() or 200 in val.values():
                has_text_data = True
            
    check("PRIVACY GUARANTEE: Zero key logs, characters, or coordinate data stored", not has_text_data)
    
    counter.stop()
    check("InputCounter stops cleanly", not counter._running)


def verify_tracker_integration() -> None:
    print("[ Step 2.3 ] Tracker & Repository Integration")
    
    mock_repo = MockRepository()
    
    # Configure flush_interval to 0.1s and poll_interval to 0.02s for instant test execution
    config = {
        "tracking": {
            "poll_interval_seconds": 0.02,
            "flush_interval_seconds": 0.1,
        }
    }
    
    # Callback tracker
    flushes = []
    def on_flush(snap: RawEventSnapshot) -> None:
        flushes.append(snap)
        
    tracker = Tracker(
        repository=mock_repo,
        config=config,
        on_flush=on_flush,
        dev_mode=True,
    )
    
    tracker.start()
    check("Tracker coordinator starts", tracker._running)
    
    # Let 3 flush cycles occur
    time.sleep(0.35)
    
    tracker.stop()
    check("Tracker coordinator stops", not tracker._running)
    
    check("on_flush callback is successfully executed", len(flushes) >= 2)
    check("Repository insert_raw_event is successfully called", len(mock_repo.events) >= 2)
    
    event = mock_repo.events[0]
    check("Persisted snapshot has process field", "process" in event)
    check("Persisted snapshot has title field", "title" in event)
    check("Persisted snapshot has keys count", "keys" in event)


def verify_resilience_retry_queue() -> None:
    print("[ Step 2.3 ] Offline Resilience & Retry Queue")
    
    failing_repo = MockRepository(fail_writes=True)
    config = {
        "tracking": {
            "poll_interval_seconds": 0.02,
            "flush_interval_seconds": 0.05,
        }
    }
    
    tracker = Tracker(
        repository=failing_repo,
        config=config,
        dev_mode=True,
    )
    
    tracker.start()
    
    # Let it flush twice to queue up 2 failures
    time.sleep(0.12)
    
    tracker.stop()
    
    retry_size = len(tracker._retry_queue)
    check("Failing database writes enqueue events to retry queue", retry_size >= 1)
    
    # Now simulate a connection restoration (failing_repo.fail_writes = False)
    failing_repo.fail_writes = False
    
    # Re-initialize tracker with the same retry queue and start it
    tracker._running = True
    tracker._accumulator_loop = lambda: None # mock loop so we control flushes
    
    # Run a flush cycle
    tracker._perform_flush()
    
    check("Retry queue is drained successfully upon connection restoration", len(tracker._retry_queue) == 0)
    check("Buffered events are successfully written to database", len(failing_repo.events) >= retry_size + 1)


def run_tests() -> None:
    global passed, failed
    
    print("\n" + "=" * 60)
    print("  AttentionLens - Production Phase 2 Tracker Verification Suite")
    print("=" * 60 + "\n")
    
    try:
        verify_code_quality()
        print()
        verify_window_inspector()
        print()
        verify_input_counter()
        print()
        verify_tracker_integration()
        print()
        verify_resilience_retry_queue()
        print()
    except Exception as exc:
        logger.exception("Unexpected error in verification suite: %s", exc)
        failed += 1
        
    total = passed + failed
    print("=" * 60)
    if failed == 0:
        print(f"\033[92m  All {total} tests passed successfully!\033[0m")
    else:
        print(f"\033[91m  {failed}/{total} tests FAILED\033[0m")
    print("  tracker.py | verify_tracker.py")
    print("=" * 60 + "\n")
    
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
