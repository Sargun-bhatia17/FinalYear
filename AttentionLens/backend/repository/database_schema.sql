-- ============================================================
-- AttentionLens — Local SQLite Database Schema (Revised Phase 1)
-- Single source of truth for all table definitions.
-- Executed by db_init.py on first launch.
-- ============================================================

-- ── Schema versioning ───────────────────────────────────────────
-- Single-row table tracking the current schema version.
-- Enables future ALTER TABLE migrations without data destruction.
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Seed version 1 only if the table is empty (first-ever init)
INSERT OR IGNORE INTO schema_version (rowid, version)
VALUES (1, 1);

-- ── Table 1: raw_window_events ──────────────────────────────────
-- Written every 5 seconds by the background event accumulator loop.
CREATE TABLE IF NOT EXISTS raw_window_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_name        TEXT NOT NULL,      -- e.g., "chrome.exe", "Code.exe"
    window_title        TEXT NOT NULL,      -- e.g., "LeetCode - Two Sum - Chrome"
    keystroke_count     INTEGER DEFAULT 0,  -- Keys pressed in this interval
    mouse_click_count   INTEGER DEFAULT 0,  -- Clicks in this interval
    scroll_delta_y      INTEGER DEFAULT 0   -- Vertical scroll pixels moved
);

-- Performance index: the accumulator loop queries by timestamp range
CREATE INDEX IF NOT EXISTS idx_rwe_timestamp
    ON raw_window_events(timestamp);

-- ── Table 2: behavioral_sessions ────────────────────────────────
-- Aggregated 60-second windows computed by the behavior engine.
CREATE TABLE IF NOT EXISTS behavioral_sessions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time           DATETIME NOT NULL,
    end_time             DATETIME NOT NULL,
    primary_process      TEXT NOT NULL,
    primary_category     TEXT NOT NULL,       -- Via Dynamic Taxonomy lookup
    scroll_velocity      REAL NOT NULL,       -- Pixels scrolled per second (S_V)
    input_density        INTEGER NOT NULL,    -- Total interactions (I_D)
    has_text_selection   BOOLEAN NOT NULL,    -- True if highlighting occurred
    calculated_state     TEXT NOT NULL,       -- "Deep Work" | "Pondering" | "Passive Leisure" | "Idle"
    attention_risk_score REAL NOT NULL        -- Fusion engine output (0.0 -> 1.0)
);

-- Performance index: timeline queries and session range lookups
CREATE INDEX IF NOT EXISTS idx_bs_start_time
    ON behavioral_sessions(start_time);

-- ── Table 3: user_taxonomy ──────────────────────────────────────
-- Personalized app/keyword -> category mapping, self-learning over time.
CREATE TABLE IF NOT EXISTS user_taxonomy (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    process_or_keyword   TEXT UNIQUE NOT NULL, -- e.g., "Figma", "LeetCode", "notion"
    assigned_category    TEXT NOT NULL,        -- "Core_Tool" | "Supporting_Tool" | "Leisure"
    confidence_weight    REAL DEFAULT 1.0      -- Modified via self-learning baseline
);

-- Performance index: fast keyword lookups during taxonomy resolution
CREATE INDEX IF NOT EXISTS idx_ut_keyword
    ON user_taxonomy(process_or_keyword);

-- ============================================================
-- NOTE: Default taxonomy seeds are loaded from taxonomy_seeds.json
-- by db_init.py's seed_taxonomy() function, NOT embedded in SQL.
-- This keeps the schema file purely structural.
-- ============================================================
