-- ============================================================
-- AttentionLens — Local SQLite Database Schema
-- Single source of truth for all table definitions.
-- This file is executed once on first launch by database_manager.py
-- ============================================================

-- Table 1: raw_window_events
-- Written every 5 seconds by the background event accumulator loop.
CREATE TABLE IF NOT EXISTS raw_window_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_name        TEXT NOT NULL,      -- e.g., "chrome.exe", "Code.exe"
    window_title        TEXT NOT NULL,      -- e.g., "LeetCode – Two Sum – Chrome"
    keystroke_count     INTEGER DEFAULT 0,  -- Keys pressed in this interval
    mouse_click_count   INTEGER DEFAULT 0,  -- Clicks in this interval
    scroll_delta_y      INTEGER DEFAULT 0   -- Vertical scroll pixels moved
);

-- Table 2: behavioral_sessions
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
    attention_risk_score REAL NOT NULL        -- Fusion engine output (0.0 → 1.0)
);

-- Table 3: user_taxonomy
-- Personalized app/keyword → category mapping, self-learning over time.
CREATE TABLE IF NOT EXISTS user_taxonomy (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    process_or_keyword   TEXT UNIQUE NOT NULL, -- e.g., "Figma", "LeetCode", "notion"
    assigned_category    TEXT NOT NULL,        -- "Core_Tool" | "Supporting_Tool" | "Leisure"
    confidence_weight    REAL DEFAULT 1.0      -- Modified via self-learning baseline
);

-- ============================================================
-- Default Taxonomy Seeds
-- Provides a working baseline on first run.
-- ============================================================
INSERT OR IGNORE INTO user_taxonomy (process_or_keyword, assigned_category, confidence_weight) VALUES
    -- Core development tools
    ('code', 'Core_Tool', 1.0),
    ('code.exe', 'Core_Tool', 1.0),
    ('vs code', 'Core_Tool', 1.0),
    ('visual studio', 'Core_Tool', 1.0),
    ('pycharm', 'Core_Tool', 1.0),
    ('pycharm64.exe', 'Core_Tool', 1.0),
    ('intellij', 'Core_Tool', 1.0),
    ('figma', 'Core_Tool', 1.0),
    ('figma.exe', 'Core_Tool', 1.0),
    ('terminal', 'Core_Tool', 1.0),
    ('powershell', 'Core_Tool', 1.0),
    ('cmd', 'Core_Tool', 1.0),
    ('sublime_text', 'Core_Tool', 1.0),
    ('atom', 'Core_Tool', 1.0),

    -- Supporting research and documentation tools
    ('github', 'Supporting_Tool', 1.0),
    ('github.com', 'Supporting_Tool', 1.0),
    ('stackoverflow', 'Supporting_Tool', 1.0),
    ('stackoverflow.com', 'Supporting_Tool', 1.0),
    ('docs', 'Supporting_Tool', 1.0),
    ('notion', 'Supporting_Tool', 1.0),
    ('notion.so', 'Supporting_Tool', 1.0),
    ('leetcode', 'Supporting_Tool', 1.0),
    ('leetcode.com', 'Supporting_Tool', 1.0),
    ('arxiv', 'Supporting_Tool', 1.0),
    ('arxiv.org', 'Supporting_Tool', 1.0),
    ('wikipedia', 'Supporting_Tool', 1.0),
    ('medium', 'Supporting_Tool', 1.0),
    ('coursera', 'Supporting_Tool', 1.0),
    ('udemy', 'Supporting_Tool', 1.0),
    ('tutorial', 'Supporting_Tool', 1.0),
    ('coursework', 'Supporting_Tool', 1.0),

    -- Leisure / distraction category
    ('youtube', 'Leisure', 1.0),
    ('youtube.com', 'Leisure', 1.0),
    ('twitter', 'Leisure', 1.0),
    ('twitter.com', 'Leisure', 1.0),
    ('x.com', 'Leisure', 1.0),
    ('reddit', 'Leisure', 1.0),
    ('reddit.com', 'Leisure', 1.0),
    ('facebook', 'Leisure', 1.0),
    ('facebook.com', 'Leisure', 1.0),
    ('instagram', 'Leisure', 1.0),
    ('instagram.com', 'Leisure', 1.0),
    ('manga', 'Leisure', 1.0),
    ('chapter', 'Leisure', 1.0),
    ('comic', 'Leisure', 1.0),
    ('netflix', 'Leisure', 1.0),
    ('netflix.com', 'Leisure', 1.0),
    ('twitch', 'Leisure', 1.0),
    ('twitch.tv', 'Leisure', 1.0),
    ('feed', 'Leisure', 1.0),
    ('scan', 'Leisure', 1.0);
