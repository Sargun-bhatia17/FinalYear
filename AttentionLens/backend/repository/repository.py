"""
repository.py
-------------
DataRepository: The single gateway between all backend logic and the SQLite database.

All database read/write operations for AttentionLens go through this class.
No SQL should be written outside this file.

Usage:
    from backend.repository.repository import DataRepository
    from backend.repository.database_manager import initialize_database

    db_path = initialize_database()
    repo = DataRepository(db_path)
    repo.insert_raw_log("Code.exe", "main.py - VSCode", 42, 3, -240)
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict

from backend.repository.database_manager import get_connection, initialize_database


class DataRepository:
    """
    Repository pattern class that encapsulates all SQLite operations for AttentionLens.

    Provides named, purpose-built methods for raw event logging, session management,
    retroactive state correction, and taxonomy management.
    """

    def __init__(self, db_path: str = None):
        """
        Initializes the repository.

        Args:
            db_path: Optional override to the database file path.
                     Defaults to data/attention_lens.db via database_manager.
        """
        self.db_path = initialize_database(db_path)

    def _conn(self) -> sqlite3.Connection:
        """Internal helper: returns a fresh connection for each operation."""
        return get_connection(self.db_path)

    # ── Raw Window Events ─────────────────────────────────────────────────────

    def insert_raw_log(
        self,
        process_name: str,
        window_title: str,
        keys: int,
        clicks: int,
        scrolls: int
    ) -> None:
        """
        Inserts a single raw 5-second polling record into raw_window_events.
        This is the primary write path called by the tracker threads.

        Args:
            process_name: Active process binary name (e.g., "Code.exe").
            window_title:  Active window title string.
            keys:          Number of keystrokes detected in this interval.
            clicks:        Number of mouse clicks detected in this interval.
            scrolls:       Vertical scroll delta (pixels, signed).
        """
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO raw_window_events
                    (process_name, window_title, keystroke_count, mouse_click_count, scroll_delta_y)
                VALUES (?, ?, ?, ?, ?)
                """,
                (process_name, window_title, keys, clicks, scrolls)
            )

    def insert_raw_event(
        self,
        process: str,
        title: str,
        keys: int,
        clicks: int,
        scroll: int
    ) -> None:
        """
        Alias for insert_raw_log matching Step 1.3 spec naming.
        Both names are valid and do the same thing.
        """
        self.insert_raw_log(process, title, keys, clicks, scroll)

    def get_last_5_minutes_events(self) -> List[sqlite3.Row]:
        """
        Fetches all raw_window_events from the last 5 minutes, ordered ascending.
        Used by the behavior engine when computing the 60-second session aggregate.

        Returns:
            List of sqlite3.Row objects with columns:
            id, timestamp, process_name, window_title,
            keystroke_count, mouse_click_count, scroll_delta_y
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, process_name, window_title,
                       keystroke_count, mouse_click_count, scroll_delta_y
                FROM raw_window_events
                WHERE timestamp >= datetime('now', '-5 minutes')
                ORDER BY timestamp ASC
                """
            ).fetchall()
        return rows

    def get_recent_raw_events(self, seconds: int = 60) -> List[sqlite3.Row]:
        """
        Fetches raw_window_events from the last N seconds.

        Args:
            seconds: Number of seconds to look back (default 60).

        Returns:
            List of sqlite3.Row objects ordered ascending by timestamp.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, process_name, window_title,
                       keystroke_count, mouse_click_count, scroll_delta_y
                FROM raw_window_events
                WHERE timestamp >= datetime('now', ?)
                ORDER BY timestamp ASC
                """,
                (f"-{seconds} seconds",)
            ).fetchall()
        return rows

    # ── Behavioral Sessions ───────────────────────────────────────────────────

    def insert_session(
        self,
        start_time: str,
        end_time: str,
        process: str,
        category: str,
        scroll_velocity: float,
        input_density: int,
        has_text_selection: bool,
        calculated_state: str,
        attention_risk_score: float
    ) -> int:
        """
        Inserts a completed 60-second behavioral session into behavioral_sessions.

        Returns:
            The auto-generated row ID of the inserted session.
        """
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO behavioral_sessions
                    (start_time, end_time, primary_process, primary_category,
                     scroll_velocity, input_density, has_text_selection,
                     calculated_state, attention_risk_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (start_time, end_time, process, category, scroll_velocity,
                 input_density, has_text_selection, calculated_state, attention_risk_score)
            )
            return cursor.lastrowid

    def update_session_state(self, session_id: int, new_state: str) -> None:
        """
        Retroactively corrects the calculated_state of a past behavioral session.
        Used exclusively by Protocol 4 — Rewriting History.

        Args:
            session_id: The row ID of the session to correct.
            new_state:  The corrected state string (e.g., "Deep Work" or "Idle_Away").
        """
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE behavioral_sessions
                SET calculated_state = ?
                WHERE id = ?
                """,
                (new_state, session_id)
            )

    def update_session_risk(self, session_id: int, new_risk_score: float) -> None:
        """
        Retroactively updates the attention_risk_score for a past session.

        Args:
            session_id:    The row ID of the session to update.
            new_risk_score: The corrected risk score (0.0 → 1.0).
        """
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE behavioral_sessions
                SET attention_risk_score = ?
                WHERE id = ?
                """,
                (new_risk_score, session_id)
            )

    def get_all_sessions(self, limit: int = 100) -> List[sqlite3.Row]:
        """
        Fetches the most recent behavioral sessions, newest first.

        Args:
            limit: Maximum number of rows to return (default 100).

        Returns:
            List of sqlite3.Row objects.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, start_time, end_time, primary_process, primary_category,
                       scroll_velocity, input_density, has_text_selection,
                       calculated_state, attention_risk_score
                FROM behavioral_sessions
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()
        return rows

    def get_session_count(self) -> int:
        """Returns the total number of behavioral sessions stored."""
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM behavioral_sessions").fetchone()
        return row[0]

    def get_last_n_sessions(self, n: int) -> List[sqlite3.Row]:
        """
        Fetches the last N sessions ordered by newest first.
        Used by the retraining daemon and Protocol 4.
        """
        return self.get_all_sessions(limit=n)

    # ── Taxonomy ──────────────────────────────────────────────────────────────

    def get_taxonomy(self) -> Dict[str, Tuple[str, float]]:
        """
        Returns the full user taxonomy as a dictionary for fast lookup.

        Returns:
            Dict mapping lowercase keyword → (category, confidence_weight).
            e.g., {"code.exe": ("Core_Tool", 1.0), "youtube": ("Leisure", 1.0)}
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT process_or_keyword, assigned_category, confidence_weight FROM user_taxonomy"
            ).fetchall()
        return {row["process_or_keyword"].lower(): (row["assigned_category"], row["confidence_weight"])
                for row in rows}

    def upsert_taxonomy(
        self,
        keyword: str,
        category: str,
        confidence: float = 1.0
    ) -> None:
        """
        Inserts or updates a keyword → category mapping in user_taxonomy.
        INSERT OR REPLACE ensures no duplicates on the unique keyword column.

        Args:
            keyword:    The app name, process name, or window title keyword.
            category:   One of "Core_Tool", "Supporting_Tool", or "Leisure".
            confidence: Trust weight for this mapping (default 1.0).
        """
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO user_taxonomy (process_or_keyword, assigned_category, confidence_weight)
                VALUES (?, ?, ?)
                ON CONFLICT(process_or_keyword) DO UPDATE SET
                    assigned_category    = excluded.assigned_category,
                    confidence_weight    = excluded.confidence_weight
                """,
                (keyword.lower().strip(), category, confidence)
            )

    def categorize(self, process_name: str, window_title: str) -> Tuple[str, float]:
        """
        Resolves a process name and window title to a taxonomy category.
        Checks both process name and title substrings against all known keywords.

        Returns:
            Tuple of (category, confidence_weight).
            Defaults to ("Supporting_Tool", 0.5) if no match is found.
        """
        taxonomy = self.get_taxonomy()
        search_text = f"{process_name} {window_title}".lower()

        best_match_category = "Supporting_Tool"
        best_match_confidence = 0.5

        for keyword, (category, confidence) in taxonomy.items():
            if keyword in search_text:
                # Give priority to more specific / longer keyword matches
                if confidence >= best_match_confidence:
                    best_match_category = category
                    best_match_confidence = confidence

        return best_match_category, best_match_confidence
