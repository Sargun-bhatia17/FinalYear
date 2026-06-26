"""
verify_db.py
------------
Revised Phase 1 end-to-end verification suite.

Tests the full stack: database_schema.sql, db_init.py, models.py, and DataRepository.
Runs against a temporary on-disk SQLite database (cleaned up after tests).

Usage:
    python backend/repository/verify_db.py
"""

import logging
import os
import sys
import tempfile

# Allow running from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.repository.db_init import initialize, get_seeds_path
from backend.repository.models import SessionRecord
from backend.repository.repository import DataRepository

# Configure logging so we can see db_init and repository logs during test
logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")

# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Test Suite ────────────────────────────────────────────────────────────────

def run_tests() -> None:
    global passed, failed

    print("\n" + "=" * 60)
    print("  AttentionLens - Revised Phase 1 Verification Suite")
    print("=" * 60 + "\n")

    # Use a temp file so we don't pollute the real database
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db", prefix="attentionlens_test_")
    os.close(tmp_fd)
    # Remove so initialize() sees it as new
    os.unlink(tmp_path)

    try:
        # ── Test 1: db_init.initialize() ──────────────────────────────────────
        print("[ Step 1.2 ] db_init.initialize()")

        db_path = initialize(tmp_path)
        check("initialize() returns a valid path", os.path.exists(db_path))
        check("initialize() returns the path we passed", db_path == tmp_path)
        print()

        # ── Test 2: Context manager ──────────────────────────────────────────
        print("[ Step 1.3 ] DataRepository as context manager")

        with DataRepository(tmp_path) as repo:
            check("DataRepository enters context cleanly", repo is not None)
            check("db_path property is accessible", repo.db_path == tmp_path)

            # ── Test 3: insert_raw_event ─────────────────────────────────────
            print()
            print("[ Step 1.3 ] insert_raw_event()")

            row_id_1 = repo.insert_raw_event("Code.exe", "main.py - VS Code", 42, 3, -240)
            check("insert_raw_event returns an int row ID", isinstance(row_id_1, int))
            check("First row ID > 0", row_id_1 > 0)

            row_id_2 = repo.insert_raw_event("chrome.exe", "LeetCode - Two Sum", 1, 0, 0)
            check("Second insert returns incremented ID", row_id_2 == row_id_1 + 1)

            row_id_3 = repo.insert_raw_event("figma.exe", "Dashboard - Figma", 5, 2, -120)
            check("Third insert succeeds", row_id_3 == row_id_2 + 1)
            print()

            # ── Test 4: get_last_n_minutes_events ────────────────────────────
            print("[ Step 1.3 ] get_last_n_minutes_events()")

            events = repo.get_last_n_minutes_events(5)
            check("Returns list (not tuples)", isinstance(events, list))
            check("Returns 3 events we just inserted", len(events) == 3)
            check("Events are dicts (not raw tuples)", isinstance(events[0], dict))
            check("Dict has 'process_name' key", "process_name" in events[0])
            check("First event process is Code.exe", events[0]["process_name"] == "Code.exe")
            check("First event keystroke_count is 42", events[0]["keystroke_count"] == 42)
            check("First event scroll_delta_y is -240", events[0]["scroll_delta_y"] == -240)
            print()

            # ── Test 5: insert_session with SessionRecord dataclass ──────────
            print("[ Step 1.3 ] insert_session(SessionRecord)")

            session = SessionRecord(
                start_time="2026-06-26 14:00:00",
                end_time="2026-06-26 14:01:00",
                primary_process="Code.exe",
                primary_category="Core_Tool",
                scroll_velocity=0.0,
                input_density=42,
                has_text_selection=False,
                calculated_state="Deep Work",
                attention_risk_score=0.1,
            )
            session_id = repo.insert_session(session)
            check("insert_session returns valid row ID", isinstance(session_id, int) and session_id > 0)

            sessions = repo.get_all_sessions(limit=10)
            check("get_all_sessions returns the inserted row", len(sessions) == 1)
            check("Session is a dict", isinstance(sessions[0], dict))
            check("Session state is 'Deep Work'", sessions[0]["calculated_state"] == "Deep Work")
            check("Risk score stored correctly", abs(sessions[0]["attention_risk_score"] - 0.1) < 1e-6)

            count = repo.get_session_count()
            check("get_session_count returns 1", count == 1)
            print()

            # ── Test 6: update_session_state (Protocol 4) ────────────────────
            print("[ Step 1.3 ] update_session_state() - Rewriting History")

            repo.update_session_state(session_id, "Idle_Away")
            updated = repo.get_all_sessions(limit=1)
            check("State rewritten to 'Idle_Away'", updated[0]["calculated_state"] == "Idle_Away")

            repo.update_session_state(session_id, "Deep Work")
            reverted = repo.get_all_sessions(limit=1)
            check("State reverted back to 'Deep Work'", reverted[0]["calculated_state"] == "Deep Work")
            print()

            # ── Test 7: Taxonomy ─────────────────────────────────────────────
            print("[ Step 1.2 ] Taxonomy seeded from taxonomy_seeds.json")

            taxonomy = repo.get_taxonomy()
            check("Taxonomy is non-empty (seeded from JSON)", len(taxonomy) > 0)
            check("'code' maps to Core_Tool", taxonomy.get("code", (None,))[0] == "Core_Tool")
            check("'youtube' maps to Leisure", taxonomy.get("youtube", (None,))[0] == "Leisure")
            check("'leetcode' maps to Supporting_Tool", taxonomy.get("leetcode", (None,))[0] == "Supporting_Tool")
            check("'slack' maps to Supporting_Tool", taxonomy.get("slack", (None,))[0] == "Supporting_Tool")
            check("'figma' maps to Core_Tool", taxonomy.get("figma", (None,))[0] == "Core_Tool")
            check("'netflix' maps to Leisure", taxonomy.get("netflix", (None,))[0] == "Leisure")
            print()

            # ── Test 8: lookup_taxonomy ──────────────────────────────────────
            print("[ Step 1.3 ] lookup_taxonomy()")

            result = repo.lookup_taxonomy("code")
            check("lookup_taxonomy('code') returns 'Core_Tool'", result == "Core_Tool")

            result_none = repo.lookup_taxonomy("unknown_xyz_12345")
            check("lookup_taxonomy returns None for unknown keyword", result_none is None)
            print()

            # ── Test 9: seed_taxonomy (idempotent) ───────────────────────────
            print("[ Step 1.3 ] seed_taxonomy() idempotent check")

            count_before = len(repo.get_taxonomy())
            seed_result = repo.seed_taxonomy()
            check("seed_taxonomy returns 0 on non-empty table", seed_result == 0)
            count_after = len(repo.get_taxonomy())
            check("Taxonomy count unchanged after re-seed", count_before == count_after)
            print()

            # ── Test 10: upsert_taxonomy ─────────────────────────────────────
            print("[ Step 1.3 ] upsert_taxonomy()")

            repo.upsert_taxonomy("obsidian", "Core_Tool", 1.0)
            check("Inserted new keyword 'obsidian'", repo.lookup_taxonomy("obsidian") == "Core_Tool")

            repo.upsert_taxonomy("obsidian", "Supporting_Tool", 0.8)
            check("Updated 'obsidian' to Supporting_Tool", repo.lookup_taxonomy("obsidian") == "Supporting_Tool")
            print()

            # ── Test 11: categorize() ────────────────────────────────────────
            print("[ Step 1.3 ] categorize() helper")

            cat, conf = repo.categorize("Code.exe", "main.py - VS Code")
            check("'Code.exe' resolves to Core_Tool", cat == "Core_Tool")

            cat2, _ = repo.categorize("chrome.exe", "Watch Netflix Season 3")
            check("'netflix' in title resolves to Leisure", cat2 == "Leisure")

            cat3, conf3 = repo.categorize("unknown_proc.exe", "random_window_12345")
            check("Unknown process defaults to Supporting_Tool", cat3 == "Supporting_Tool")
            check("Unknown process has confidence < 1.0", conf3 < 1.0)
            print()

            # ── Test 12: daily_prune ─────────────────────────────────────────
            print("[ Step 1.3 ] daily_prune()")

            # All events were just inserted, so pruning 30 days should delete 0
            pruned = repo.daily_prune(retain_days=30)
            check("daily_prune(30) deletes 0 recent events", pruned == 0)

            # Prune with 0 days should delete everything
            pruned_all = repo.daily_prune(retain_days=0)
            check("daily_prune(0) deletes all raw events", pruned_all >= 3)

            remaining = repo.get_last_n_minutes_events(60)
            check("No raw events remain after prune(0)", len(remaining) == 0)

            # Sessions should be untouched
            check("Sessions NOT pruned", repo.get_session_count() == 1)
            print()

        # ── Test 13: context manager __exit__ ────────────────────────────────
        print("[ Step 1.3 ] Context manager __exit__")
        check("Exited context manager without error", True)
        print()

    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        # WAL and SHM files
        for suffix in ("-wal", "-shm"):
            wal_path = tmp_path + suffix
            if os.path.exists(wal_path):
                os.unlink(wal_path)

    # ── Summary ──────────────────────────────────────────────────────────────
    total = passed + failed
    print("=" * 60)
    if failed == 0:
        print(f"\033[92m  All {total} tests passed successfully!\033[0m")
    else:
        print(f"\033[91m  {failed}/{total} tests FAILED\033[0m")
    print(f"  database_schema.sql | db_init.py | models.py | repository.py")
    print("=" * 60 + "\n")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
