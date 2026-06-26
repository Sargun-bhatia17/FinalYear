import os
import sqlite3
from datetime import datetime

class ActivityRepository:
    def __init__(self, db_path=None):
        if db_path is None:
            # Locate relative to the engine directory: engine/../data/attentionlens.db
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "attentionlens.db")
        else:
            self.db_path = db_path
            
        self.initialize_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def initialize_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Table 1: raw_window_events
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_window_events (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP,
                process_name        TEXT NOT NULL,
                window_title        TEXT NOT NULL,
                keystroke_count     INTEGER DEFAULT 0,
                mouse_click_count   INTEGER DEFAULT 0,
                scroll_delta_y      INTEGER DEFAULT 0
            );
            """)
            
            # Table 2: behavioral_sessions
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS behavioral_sessions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time          DATETIME NOT NULL,
                end_time            DATETIME NOT NULL,
                primary_process     TEXT NOT NULL,
                primary_category    TEXT NOT NULL,
                scroll_velocity     REAL NOT NULL,
                input_density       INTEGER NOT NULL,
                has_text_selection  BOOLEAN NOT NULL,
                calculated_state    TEXT NOT NULL,
                attention_risk_score REAL NOT NULL
            );
            """)
            
            # Table 3: user_taxonomy
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_taxonomy (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                process_or_keyword   TEXT UNIQUE NOT NULL,
                assigned_category    TEXT NOT NULL,
                confidence_weight    REAL DEFAULT 1.0
            );
            """)
            
            # Seed default taxonomy if empty
            cursor.execute("SELECT COUNT(*) FROM user_taxonomy")
            if cursor.fetchone()[0] == 0:
                defaults = [
                    ("code", "Core_Tool", 1.0),
                    ("vs code", "Core_Tool", 1.0),
                    ("visual studio", "Core_Tool", 1.0),
                    ("pycharm", "Core_Tool", 1.0),
                    ("figma", "Core_Tool", 1.0),
                    ("github", "Core_Tool", 1.0),
                    ("stackoverflow", "Supporting_Tool", 1.0),
                    ("docs", "Supporting_Tool", 1.0),
                    ("notion", "Supporting_Tool", 1.0),
                    ("leetcode", "Supporting_Tool", 1.0),
                    ("youtube", "Leisure", 1.0),
                    ("twitter", "Leisure", 1.0),
                    ("reddit", "Leisure", 1.0),
                    ("facebook", "Leisure", 1.0),
                    ("manga", "Leisure", 1.0),
                    ("chapter", "Leisure", 1.0),
                ]
                cursor.executemany(
                    "INSERT INTO user_taxonomy (process_or_keyword, assigned_category, confidence_weight) VALUES (?, ?, ?)",
                    defaults
                )
            conn.commit()

    # Raw window events operations
    def insert_raw_window_event(self, process_name, window_title, keystrokes, clicks, scroll_y):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO raw_window_events (process_name, window_title, keystroke_count, mouse_click_count, scroll_delta_y)
            VALUES (?, ?, ?, ?, ?)
            """, (process_name, window_title, keystrokes, clicks, scroll_y))
            conn.commit()

    def get_recent_raw_events(self, seconds=60):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Fetch events from the last N seconds
            cursor.execute("""
            SELECT timestamp, process_name, window_title, keystroke_count, mouse_click_count, scroll_delta_y
            FROM raw_window_events
            WHERE timestamp >= datetime('now', ?)
            ORDER BY timestamp ASC
            """, (f"-{seconds} seconds",))
            return cursor.fetchall()

    # Behavioral session operations
    def insert_behavioral_session(self, start_time, end_time, primary_process, primary_category, scroll_velocity, input_density, has_selection, calculated_state, risk_score):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO behavioral_sessions (start_time, end_time, primary_process, primary_category, scroll_velocity, input_density, has_text_selection, calculated_state, attention_risk_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (start_time, end_time, primary_process, primary_category, scroll_velocity, input_density, has_selection, calculated_state, risk_score))
            conn.commit()

    def get_session_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM behavioral_sessions")
            return cursor.fetchone()[0]

    def get_all_sessions(self, limit=100):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, start_time, end_time, primary_process, primary_category, scroll_velocity, input_density, has_text_selection, calculated_state, attention_risk_score
            FROM behavioral_sessions
            ORDER BY id DESC
            LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    # Taxonomy lookup and update
    def get_taxonomy(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT process_or_keyword, assigned_category, confidence_weight FROM user_taxonomy")
            rows = cursor.fetchall()
            return {row[0].lower(): (row[1], row[2]) for row in rows}

    def add_or_update_taxonomy(self, process_or_keyword, category, confidence=1.0):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO user_taxonomy (process_or_keyword, assigned_category, confidence_weight)
            VALUES (?, ?, ?)
            ON CONFLICT(process_or_keyword) DO UPDATE SET
                assigned_category=excluded.assigned_category,
                confidence_weight=excluded.confidence_weight
            """, (process_or_keyword.lower(), category, confidence))
            conn.commit()
