"""
repository.py (Revised Phase 1, Step 1.3)
------------------------------------------
DataRepository: The single gateway between all backend logic and the SQLite database.

Code quality contract:
  - Context manager (``__enter__`` / ``__exit__``)
  - Single persistent ``sqlite3.Connection`` (check_same_thread=False, isolation_level=None)
  - Every public method is fully type-annotated
  - No bare ``except:`` — only specific exception types
  - Parameterized queries exclusively (``?`` placeholders, never string formatting)
  - Methods are 15-30 lines max; longer logic is extracted to private helpers
  - ``logging`` module only — zero ``print()`` statements
  - Zero module-level side effects; instantiation is the only trigger

Usage::

    from backend.repository.repository import DataRepository

    with DataRepository() as repo:
        row_id = repo.insert_raw_event("Code.exe", "main.py - VSCode", 42, 3, -240)
        events = repo.get_last_n_minutes_events(5)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from backend.repository.db_init import initialize, get_db_path, get_seeds_path
from backend.repository.models import SessionRecord, RawEventRecord

logger = logging.getLogger(__name__)


class DataRepository:
    """
    Repository-pattern gateway to the AttentionLens SQLite database.

    Implements the context-manager protocol for deterministic cleanup.
    All SQL uses parameterized ``?`` placeholders — never string interpolation.
    """

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Opens (or creates) the database and establishes a persistent connection.

        Args:
            db_path: Optional override to the database file path.
                     Defaults to ``data/attention_lens.db`` via db_init.
        """
        self._db_path: str = initialize(db_path)
        self._conn: sqlite3.Connection = self._open_connection()
        logger.info("DataRepository initialized — db: %s", self._db_path)

    def _open_connection(self) -> sqlite3.Connection:
        """Creates the single persistent connection with required settings."""
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,       # autocommit OFF — we use explicit tx
        )
        conn.row_factory = sqlite3.Row
        # Re-apply pragmas on the persistent connection
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA cache_size=-16000;")
        return conn

    def __enter__(self) -> DataRepository:
        """Context-manager entry — returns self."""
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None,
                 exc_tb: object | None) -> None:
        """Context-manager exit — closes the persistent connection."""
        self.close()

    def close(self) -> None:
        """Explicitly closes the persistent database connection."""
        if self._conn:
            self._conn.close()
            logger.info("DataRepository connection closed.")

    @property
    def db_path(self) -> str:
        """Read-only access to the database file path."""
        return self._db_path

    # ── Raw Window Events ─────────────────────────────────────────────────────

    def insert_raw_event(
        self,
        process: str,
        title: str,
        keys: int,
        clicks: int,
        scroll: int,
    ) -> int:
        """
        Inserts a single 5-second raw polling record into raw_window_events.

        Args:
            process: Active process binary name (e.g., "Code.exe").
            title:   Active window title string.
            keys:    Number of keystrokes detected in this interval.
            clicks:  Number of mouse clicks detected in this interval.
            scroll:  Vertical scroll delta (pixels, signed integer).

        Returns:
            The auto-generated row ID of the inserted record.
        """
        cursor = self._conn.execute(
            """
            INSERT INTO raw_window_events
                (process_name, window_title, keystroke_count,
                 mouse_click_count, scroll_delta_y)
            VALUES (?, ?, ?, ?, ?)
            """,
            (process, title, keys, clicks, scroll),
        )
        self._conn.commit()
        row_id = cursor.lastrowid
        logger.debug("Inserted raw event id=%d process=%s", row_id, process)
        return row_id

    def get_last_n_minutes_events(self, n: int = 5) -> list[dict]:
        """
        Fetches raw_window_events from the last *n* minutes.

        Args:
            n: Number of minutes to look back (default 5).

        Returns:
            List of typed dicts (not raw tuples) with all event columns.
        """
        rows = self._conn.execute(
            """
            SELECT id, timestamp, process_name, window_title,
                   keystroke_count, mouse_click_count, scroll_delta_y
            FROM raw_window_events
            WHERE timestamp >= datetime('now', ?)
            ORDER BY timestamp ASC
            """,
            (f"-{n} minutes",),
        ).fetchall()

        return [self._row_to_event_dict(row) for row in rows]

    def _row_to_event_dict(self, row: sqlite3.Row) -> dict:
        """Converts a sqlite3.Row into a plain typed dict."""
        return {
            "id":                int(row["id"]),
            "timestamp":         str(row["timestamp"]),
            "process_name":      str(row["process_name"]),
            "window_title":      str(row["window_title"]),
            "keystroke_count":   int(row["keystroke_count"]),
            "mouse_click_count": int(row["mouse_click_count"]),
            "scroll_delta_y":    int(row["scroll_delta_y"]),
        }

    # ── Behavioral Sessions ───────────────────────────────────────────────────

    def insert_session(self, session: SessionRecord) -> int:
        """
        Inserts a completed 60-second behavioral session.

        Args:
            session: A ``SessionRecord`` dataclass (not raw args).

        Returns:
            The auto-generated row ID of the inserted session.
        """
        cursor = self._conn.execute(
            """
            INSERT INTO behavioral_sessions
                (start_time, end_time, primary_process, primary_category,
                 scroll_velocity, input_density, has_text_selection,
                 calculated_state, attention_risk_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._session_to_tuple(session),
        )
        self._conn.commit()
        row_id = cursor.lastrowid
        logger.debug("Inserted session id=%d state=%s", row_id, session.calculated_state)
        return row_id

    def _session_to_tuple(self, s: SessionRecord) -> tuple:
        """Extracts a SessionRecord into the column-ordered tuple for INSERT."""
        return (
            s.start_time, s.end_time, s.primary_process, s.primary_category,
            s.scroll_velocity, s.input_density, s.has_text_selection,
            s.calculated_state, s.attention_risk_score,
        )

    def update_session_state(self, session_id: int, new_state: str, risk_score: Optional[float] = None) -> None:
        """
        Retroactively corrects the calculated_state of a past session.
        Used exclusively by Protocol 4 — Rewriting History.

        Args:
            session_id: The row ID of the session to correct.
            new_state:  The corrected state string (e.g., "Deep Work" or "Idle_Away").
            risk_score: Optional risk score to set.
        """
        if risk_score is not None:
            self._conn.execute(
                "UPDATE behavioral_sessions SET calculated_state = ?, attention_risk_score = ? WHERE id = ?",
                (new_state, risk_score, session_id),
            )
        else:
            self._conn.execute(
                "UPDATE behavioral_sessions SET calculated_state = ? WHERE id = ?",
                (new_state, session_id),
            )
        self._conn.commit()
        logger.info("Rewrote session %d state -> %s (risk -> %s)", session_id, new_state, risk_score)

    def get_all_sessions(self, limit: int = 100) -> list[dict]:
        """
        Fetches the most recent behavioral sessions, newest first.

        Args:
            limit: Maximum number of rows to return (default 100).

        Returns:
            List of typed dicts with all session columns.
        """
        rows = self._conn.execute(
            """
            SELECT id, start_time, end_time, primary_process, primary_category,
                   scroll_velocity, input_density, has_text_selection,
                   calculated_state, attention_risk_score
            FROM behavioral_sessions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [self._row_to_session_dict(row) for row in rows]

    def _row_to_session_dict(self, row: sqlite3.Row) -> dict:
        """Converts a sqlite3.Row into a plain typed dict for sessions."""
        return {
            "id":                   int(row["id"]),
            "start_time":           str(row["start_time"]),
            "end_time":             str(row["end_time"]),
            "primary_process":      str(row["primary_process"]),
            "primary_category":     str(row["primary_category"]),
            "scroll_velocity":      float(row["scroll_velocity"]),
            "input_density":        float(row["input_density"]),
            "has_text_selection":   bool(row["has_text_selection"]),
            "calculated_state":     str(row["calculated_state"]),
            "attention_risk_score": float(row["attention_risk_score"]),
        }

    def get_session_count(self) -> int:
        """Returns the total number of behavioral sessions stored."""
        row = self._conn.execute("SELECT COUNT(*) FROM behavioral_sessions").fetchone()
        return int(row[0])

    def get_pending_unknown_sessions(self) -> list[dict]:
        """
        Fetches all sessions with calculated_state='Unknown', ordered oldest-first.

        These are sessions awaiting retroactive state resolution by Protocol P4.
        Returns the full session dict so the rule engine can inspect age and category.
        """
        rows = self._conn.execute(
            """
            SELECT id, start_time, end_time, primary_process, primary_category,
                   scroll_velocity, input_density, has_text_selection,
                   calculated_state, attention_risk_score
            FROM behavioral_sessions
            WHERE calculated_state = 'Unknown'
            ORDER BY start_time ASC
            """
        ).fetchall()
        return [self._row_to_session_dict(row) for row in rows]

    # ── Taxonomy ──────────────────────────────────────────────────────────────

    def lookup_taxonomy(self, process_or_keyword: str) -> str | None:
        """
        Looks up a single keyword in the taxonomy table.

        Args:
            process_or_keyword: The process name or window-title keyword to look up.

        Returns:
            The category string ("Core_Tool", "Supporting_Tool", "Leisure")
            or ``None`` if the keyword is not in the taxonomy.
        """
        row = self._conn.execute(
            "SELECT assigned_category FROM user_taxonomy WHERE process_or_keyword = ?",
            (process_or_keyword.lower().strip(),),
        ).fetchone()

        if row is None:
            return None
        return str(row["assigned_category"])

    def get_taxonomy(self) -> dict[str, tuple[str, float]]:
        """
        Returns the full taxonomy as a dictionary for batch lookups.

        Returns:
            Dict mapping lowercase keyword -> (category, confidence_weight).
        """
        rows = self._conn.execute(
            "SELECT process_or_keyword, assigned_category, confidence_weight "
            "FROM user_taxonomy"
        ).fetchall()

        return {
            str(row["process_or_keyword"]).lower(): (
                str(row["assigned_category"]),
                float(row["confidence_weight"]),
            )
            for row in rows
        }

    def get_taxonomy_snapshot(self) -> dict[str, str]:
        """
        Returns a simplified taxonomy dictionary mapping lowercase process/keyword -> category.

        Returns:
            Dict mapping lowercase process name or keyword -> category string.
        """
        taxonomy = self.get_taxonomy()
        return {k: cat for k, (cat, _) in taxonomy.items()}

    def upsert_taxonomy(
        self,
        keyword: str,
        category: str,
        confidence: float = 1.0,
    ) -> None:
        """
        Inserts or updates a single taxonomy entry.

        Args:
            keyword:    The app name, process name, or title keyword.
            category:   One of "Core_Tool", "Supporting_Tool", or "Leisure".
            confidence: Trust weight for this mapping (default 1.0).
        """
        self._conn.execute(
            """
            INSERT INTO user_taxonomy (process_or_keyword, assigned_category, confidence_weight)
            VALUES (?, ?, ?)
            ON CONFLICT(process_or_keyword) DO UPDATE SET
                assigned_category  = excluded.assigned_category,
                confidence_weight  = excluded.confidence_weight
            """,
            (keyword.lower().strip(), category, confidence),
        )
        self._conn.commit()
        logger.debug("Upserted taxonomy: %s -> %s (%.2f)", keyword, category, confidence)

    def seed_taxonomy(self, seeds_path: Optional[Path] = None) -> int:
        """
        Bulk-inserts taxonomy seeds from a JSON file. Skips on conflict.

        Args:
            seeds_path: Path to the JSON seeds file.
                        Defaults to taxonomy_seeds.json in this directory.

        Returns:
            Count of rows inserted (0 if table was already populated).
        """
        if seeds_path is None:
            seeds_path = get_seeds_path()

        return self._load_and_insert_seeds(seeds_path)

    def _load_and_insert_seeds(self, seeds_path: Path) -> int:
        """Reads JSON and performs the bulk insert."""
        if not seeds_path.exists():
            logger.warning("Seeds file not found: %s", seeds_path)
            return 0

        existing = self._conn.execute("SELECT COUNT(*) FROM user_taxonomy").fetchone()[0]
        if existing > 0:
            logger.info("Taxonomy has %d entries — skipping seed.", existing)
            return 0

        with open(seeds_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        seeds = data.get("seeds", [])
        rows = [(s["keyword"].lower().strip(), s["category"], s["confidence"]) for s in seeds]

        self._conn.executemany(
            "INSERT OR IGNORE INTO user_taxonomy "
            "(process_or_keyword, assigned_category, confidence_weight) VALUES (?, ?, ?)",
            rows,
        )
        self._conn.commit()

        count = self._conn.execute("SELECT COUNT(*) FROM user_taxonomy").fetchone()[0]
        logger.info("Taxonomy seeded: %d rows from %s", count, seeds_path.name)
        return count

    # ── Maintenance ───────────────────────────────────────────────────────────

    def daily_prune(self, retain_days: int = 30) -> int:
        """
        Deletes old raw_window_events older than *retain_days*.

        This prevents the raw events table from growing unbounded on disk.
        Behavioral sessions are never pruned (they are the processed output).

        Args:
            retain_days: Number of days of raw events to keep (default 30).

        Returns:
            Number of rows deleted.
        """
        cursor = self._conn.execute(
            "DELETE FROM raw_window_events WHERE timestamp <= datetime('now', ?)",
            (f"-{retain_days} days",),
        )
        self._conn.commit()
        deleted = cursor.rowcount
        logger.info(
            "Daily prune: deleted %d raw events older than %d days.",
            deleted, retain_days,
        )
        return deleted

    # ── Categorize helper ─────────────────────────────────────────────────────

    def categorize(self, process_name: str, window_title: str) -> tuple[str, float]:
        """
        Resolves a process name + window title to a taxonomy category.

        Checks both process name and title substrings against all known keywords.
        Prioritizes longer (more specific) keyword matches.

        Returns:
            Tuple of (category, confidence_weight).
            Defaults to ("Supporting_Tool", 0.5) if no match is found.
        """
        taxonomy = self.get_taxonomy()
        search_text = f"{process_name} {window_title}".lower()
        return self._best_match(taxonomy, search_text)

    def _best_match(
        self,
        taxonomy: dict[str, tuple[str, float]],
        search_text: str,
    ) -> tuple[str, float]:
        """Finds the highest-confidence keyword match in the search text."""
        best_cat = "Supporting_Tool"
        best_conf = 0.5

        for keyword, (category, confidence) in taxonomy.items():
            if keyword in search_text and confidence >= best_conf:
                best_cat = category
                best_conf = confidence

        return best_cat, best_conf
