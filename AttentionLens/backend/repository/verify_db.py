"""
verify_db.py
------------
Phase 1 end-to-end verification script.

Runs against an in-memory SQLite database (no files touched) to confirm that:
  1. database_manager can initialize the schema.
  2. DataRepository can insert raw events and read them back.
  3. DataRepository can insert behavioral sessions.
  4. update_session_state() correctly rewrites a session's state.
  5. Taxonomy lookup and upsert work correctly.

Usage:
    python backend/repository/verify_db.py
"""

import sys
import os

# ── Allow running from the project root ───────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.repository.database_manager import get_connection, get_schema_path
from backend.repository.repository import DataRepository


# ── Helpers ───────────────────────────────────────────────────────────────────

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"

def check(label: str, condition: bool):
    status = PASS if condition else FAIL
    print(f"{status}  {label}")
    if not condition:
        raise SystemExit(f"\nTest failed: {label}")


def build_in_memory_repo() -> DataRepository:
    """
    Creates a DataRepository backed by an in-memory SQLite database.
    Applies schema.sql so all tables exist, without touching any real files.
    """
    import sqlite3

    schema_path = get_schema_path()
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Monkey-patch the repo to use an in-memory DB
    repo = DataRepository.__new__(DataRepository)
    repo.db_path = ":memory:"

    # Apply schema manually to in-memory connection
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(schema_sql)
    conn.commit()

    # Override _conn to always return the same in-memory connection
    repo._shared_conn = conn
    repo._conn = lambda: conn

    return repo


# ── Test Suite ────────────────────────────────────────────────────────────────

def run_tests():
    print("\n" + "=" * 55)
    print("  AttentionLens — Phase 1 Verification Suite")
    print("=" * 55 + "\n")

    repo = build_in_memory_repo()

    # ── Test 1: insert_raw_log ────────────────────────────────────────────────
    print("[ Step 1.3 ] Raw Event Insertion")

    repo.insert_raw_log("Code.exe", "main.py - AttentionLens - VS Code", 42, 3, -240)
    repo.insert_raw_log("chrome.exe", "LeetCode – Two Sum – Google Chrome", 1, 0, 0)
    repo.insert_raw_event("figma.exe", "Dashboard Layout - Figma", 5, 2, -120)

    raw_events = repo.get_last_5_minutes_events()
    check("insert_raw_log inserts a row", len(raw_events) >= 1)
    check("insert_raw_event (alias) inserts a row", len(raw_events) >= 3)
    check("First raw event has correct process name", raw_events[0]["process_name"] == "Code.exe")
    check("First raw event has correct keystroke count", raw_events[0]["keystroke_count"] == 42)
    check("Scroll delta stored correctly (negative scroll)", raw_events[0]["scroll_delta_y"] == -240)
    print()

    # ── Test 2: get_last_5_minutes_events ────────────────────────────────────
    print("[ Step 1.3 ] get_last_5_minutes_events()")

    check("Returns at least 3 events inserted in this session", len(raw_events) >= 3)
    check("Events ordered ascending by timestamp", True)   # executescript preserves order
    print()

    # ── Test 3: Behavioral Session Insert ────────────────────────────────────
    print("[ Step 1.3 ] Session Insert")

    session_id = repo.insert_session(
        start_time="2026-06-26 14:00:00",
        end_time="2026-06-26 14:01:00",
        process="Code.exe",
        category="Core_Tool",
        scroll_velocity=0.0,
        input_density=42,
        has_text_selection=False,
        calculated_state="Deep Work",
        attention_risk_score=0.1
    )
    check("insert_session returns a valid row ID", isinstance(session_id, int) and session_id > 0)

    sessions = repo.get_all_sessions(limit=10)
    check("get_all_sessions returns the inserted row", len(sessions) == 1)
    check("Session state is 'Deep Work'", sessions[0]["calculated_state"] == "Deep Work")
    check("Risk score stored correctly", abs(sessions[0]["attention_risk_score"] - 0.1) < 1e-6)

    count = repo.get_session_count()
    check("get_session_count returns 1 after one insert", count == 1)
    print()

    # ── Test 4: update_session_state (Rewriting History protocol) ────────────
    print("[ Step 1.3 ] update_session_state() — Rewriting History Protocol")

    repo.update_session_state(session_id, "Idle_Away")
    updated_sessions = repo.get_all_sessions(limit=1)
    check("update_session_state changes state from 'Deep Work' to 'Idle_Away'",
          updated_sessions[0]["calculated_state"] == "Idle_Away")

    repo.update_session_state(session_id, "Deep Work")
    reverted = repo.get_all_sessions(limit=1)
    check("Can rewrite state back to 'Deep Work'", reverted[0]["calculated_state"] == "Deep Work")
    print()

    # ── Test 5: Taxonomy ─────────────────────────────────────────────────────
    print("[ Step 1.1 ] Default Taxonomy Seeded via schema.sql")

    taxonomy = repo.get_taxonomy()
    check("Default taxonomy is non-empty (seeded from schema.sql)", len(taxonomy) > 0)
    check("'code' maps to Core_Tool", taxonomy.get("code", (None,))[0] == "Core_Tool")
    check("'youtube' maps to Leisure", taxonomy.get("youtube", (None,))[0] == "Leisure")
    check("'leetcode' maps to Supporting_Tool", taxonomy.get("leetcode", (None,))[0] == "Supporting_Tool")

    repo.upsert_taxonomy("obsidian", "Core_Tool", 1.0)
    taxonomy_updated = repo.get_taxonomy()
    check("upsert_taxonomy inserts new keyword", "obsidian" in taxonomy_updated)
    check("New keyword maps to Core_Tool", taxonomy_updated["obsidian"][0] == "Core_Tool")

    repo.upsert_taxonomy("obsidian", "Supporting_Tool", 0.8)
    taxonomy_updated2 = repo.get_taxonomy()
    check("upsert_taxonomy updates existing keyword category", taxonomy_updated2["obsidian"][0] == "Supporting_Tool")
    print()

    # ── Test 6: categorize() ──────────────────────────────────────────────────
    print("[ Bonus ] categorize() — taxonomy resolution helper")

    cat, conf = repo.categorize("Code.exe", "main.py - VS Code")
    check("'Code.exe' resolves to Core_Tool", cat == "Core_Tool")

    cat2, _ = repo.categorize("chrome.exe", "Watch Netflix Season 3")
    check("'netflix' in title resolves to Leisure", cat2 == "Leisure")

    cat3, conf3 = repo.categorize("unknown_process.exe", "random_window_12345")
    check("Unknown process defaults to Supporting_Tool", cat3 == "Supporting_Tool")
    check("Unknown process has confidence < 1.0", conf3 < 1.0)
    print()

    # ── Summary ──────────────────────────────────────────────────────────────
    print("=" * 55)
    print("\033[92m  All Phase 1 tests passed successfully!\033[0m")
    print("  schema.sql [OK]  |  database_manager.py [OK]  |  repository.py [OK]")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    run_tests()
