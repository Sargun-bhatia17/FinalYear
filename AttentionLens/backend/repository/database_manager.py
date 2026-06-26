"""
database_manager.py
-------------------
Handles all database connection lifecycle concerns for AttentionLens.

Responsibilities:
- Resolving the database file path relative to the project root.
- Providing a factory function for SQLite connections.
- Auto-initializing the database (running schema.sql) on first launch.

No business logic lives here. All data operations belong in repository.py.
"""

import os
import sqlite3


# ── Path resolution ──────────────────────────────────────────────────────────

def get_project_root() -> str:
    """Returns the absolute path to the AttentionLens project root directory."""
    # This file: backend/repository/database_manager.py
    # Project root is two levels up.
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_db_path() -> str:
    """Returns the absolute path to attention_lens.db inside the data/ folder."""
    data_dir = os.path.join(get_project_root(), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "attention_lens.db")


def get_schema_path() -> str:
    """Returns the absolute path to schema.sql."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


# ── Connection factory ────────────────────────────────────────────────────────

def get_connection(db_path: str = None) -> sqlite3.Connection:
    """
    Creates and returns a SQLite connection.

    Args:
        db_path: Optional override path to the database file.
                 Defaults to the project-standard data/attention_lens.db.

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row for
        named column access and check_same_thread=False for multi-threaded use.
    """
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row   # allows row["column_name"] access
    conn.execute("PRAGMA journal_mode=WAL;")  # Write-Ahead Logging for concurrency
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ── Database initialization ───────────────────────────────────────────────────

def initialize_database(db_path: str = None) -> str:
    """
    Checks whether the database file exists and has been initialized.
    If not, reads schema.sql and executes it to create all tables and
    seed the default taxonomy rows.

    Args:
        db_path: Optional override path. Defaults to data/attention_lens.db.

    Returns:
        The absolute path to the initialized database file.
    """
    if db_path is None:
        db_path = get_db_path()

    db_is_new = not os.path.exists(db_path) or os.path.getsize(db_path) == 0

    conn = get_connection(db_path)
    try:
        if db_is_new:
            print(f"[DB] New database detected. Initializing schema at: {db_path}")
            schema_path = get_schema_path()

            if not os.path.exists(schema_path):
                raise FileNotFoundError(
                    f"[DB] schema.sql not found at: {schema_path}. "
                    "Ensure schema.sql is present in backend/repository/."
                )

            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()

            conn.executescript(schema_sql)
            conn.commit()
            print("[DB] Schema applied successfully. All tables created and taxonomy seeded.")
        else:
            # DB exists — still run CREATE IF NOT EXISTS to handle partial states
            schema_path = get_schema_path()
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            conn.executescript(schema_sql)
            conn.commit()
            print(f"[DB] Existing database loaded from: {db_path}")
    finally:
        conn.close()

    return db_path
