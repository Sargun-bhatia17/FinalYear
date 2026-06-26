"""
db_init.py
----------
Database initialization for AttentionLens (Revised Phase 1, Step 1.2).

Responsibilities:
  1. Create/locate the SQLite database file.
  2. Execute database_schema.sql to create all tables and indexes.
  3. Apply performance-critical PRAGMA settings in the correct order.
  4. Call seed_taxonomy() to bulk-insert from taxonomy_seeds.json if empty.

Zero module-level side effects — nothing happens until initialize() is called.

Usage:
    from backend.repository.db_init import initialize

    db_path = initialize()
"""

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Path Resolution ──────────────────────────────────────────────────────────

def get_project_root() -> Path:
    """Returns the AttentionLens project root (two levels above this file)."""
    return Path(__file__).resolve().parent.parent.parent


def get_db_path() -> Path:
    """Returns the path to data/attention_lens.db, creating data/ if needed."""
    data_dir = get_project_root() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "attention_lens.db"


def get_schema_path() -> Path:
    """Returns the path to database_schema.sql in the same directory."""
    return Path(__file__).resolve().parent / "database_schema.sql"


def get_seeds_path() -> Path:
    """Returns the path to taxonomy_seeds.json in the same directory."""
    return Path(__file__).resolve().parent / "taxonomy_seeds.json"


# ── PRAGMA Application ───────────────────────────────────────────────────────

def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """
    Applies performance-critical SQLite PRAGMA settings in order.

    These must be executed after opening the connection but before
    any schema or data operations.

    Order matters:
      1. journal_mode=WAL  — Write-Ahead Logging for concurrent reads
      2. synchronous=NORMAL — Balanced durability vs. speed (safe with WAL)
      3. foreign_keys=ON    — Enforce referential integrity
      4. cache_size=-16000  — 16MB page cache (negative = KB units)
    """
    pragmas = [
        "PRAGMA journal_mode=WAL;",
        "PRAGMA synchronous=NORMAL;",
        "PRAGMA foreign_keys=ON;",
        "PRAGMA cache_size=-16000;",
    ]
    for pragma in pragmas:
        conn.execute(pragma)
        logger.debug("Applied: %s", pragma.strip())

    logger.info("All PRAGMA settings applied successfully.")


# ── Schema Application ───────────────────────────────────────────────────────

def _apply_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    """Reads and executes database_schema.sql to create tables and indexes."""
    if not schema_path.exists():
        raise FileNotFoundError(
            f"database_schema.sql not found at: {schema_path}. "
            "Ensure it is present in backend/repository/."
        )

    schema_sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    logger.info("Schema applied from: %s", schema_path.name)


# ── Taxonomy Seeding ─────────────────────────────────────────────────────────

def seed_taxonomy(conn: sqlite3.Connection, seeds_path: Optional[Path] = None) -> int:
    """
    Checks if user_taxonomy is empty, and if so, bulk-inserts from
    taxonomy_seeds.json. Skips rows that already exist (ON CONFLICT IGNORE).

    Args:
        conn:       An active SQLite connection.
        seeds_path: Path to the JSON seeds file. Defaults to same directory.

    Returns:
        Number of rows inserted (0 if table was already populated).
    """
    if seeds_path is None:
        seeds_path = get_seeds_path()

    # Check if taxonomy already has data
    cursor = conn.execute("SELECT COUNT(*) FROM user_taxonomy")
    existing_count = cursor.fetchone()[0]

    if existing_count > 0:
        logger.info(
            "Taxonomy already contains %d entries — skipping seed.",
            existing_count,
        )
        return 0

    # Load seeds from JSON
    if not seeds_path.exists():
        logger.warning(
            "taxonomy_seeds.json not found at: %s — taxonomy will be empty.",
            seeds_path,
        )
        return 0

    with open(seeds_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    seeds = data.get("seeds", [])
    if not seeds:
        logger.warning("taxonomy_seeds.json contains no seed entries.")
        return 0

    # Bulk insert with ON CONFLICT IGNORE for safety
    insert_sql = """
        INSERT OR IGNORE INTO user_taxonomy
            (process_or_keyword, assigned_category, confidence_weight)
        VALUES (?, ?, ?)
    """

    rows_to_insert = [
        (entry["keyword"].lower().strip(), entry["category"], entry["confidence"])
        for entry in seeds
    ]

    conn.executemany(insert_sql, rows_to_insert)
    conn.commit()

    inserted = conn.execute("SELECT COUNT(*) FROM user_taxonomy").fetchone()[0]
    logger.info(
        "Taxonomy seeded: %d rows inserted from %s.",
        inserted,
        seeds_path.name,
    )
    return inserted


# ── Main Initialization Entry Point ──────────────────────────────────────────

def initialize(db_path: Optional[str] = None) -> str:
    """
    Complete database initialization sequence:
      1. Resolve or create the database file.
      2. Open a connection with check_same_thread=False.
      3. Apply all PRAGMAs in order.
      4. Execute database_schema.sql (CREATE IF NOT EXISTS + indexes).
      5. Seed taxonomy from taxonomy_seeds.json if the table is empty.

    Args:
        db_path: Optional override. Defaults to data/attention_lens.db.

    Returns:
        The absolute path to the initialized database file as a string.
    """
    if db_path is None:
        resolved_path = get_db_path()
    else:
        resolved_path = Path(db_path)

    db_path_str = str(resolved_path)
    is_new = not resolved_path.exists() or resolved_path.stat().st_size == 0

    conn = sqlite3.connect(db_path_str, check_same_thread=False)
    try:
        # Step 1: PRAGMAs first
        _apply_pragmas(conn)

        # Step 2: Schema (idempotent — CREATE IF NOT EXISTS)
        _apply_schema(conn, get_schema_path())

        # Step 3: Seed taxonomy if first run
        seed_count = seed_taxonomy(conn)

        if is_new:
            logger.info("New database initialized at: %s", db_path_str)
        else:
            logger.info("Existing database loaded from: %s", db_path_str)

    except sqlite3.Error as e:
        logger.error("Database initialization failed: %s", e)
        raise
    finally:
        conn.close()

    return db_path_str
