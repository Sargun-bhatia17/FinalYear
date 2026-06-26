import re
from typing import Tuple, Dict, Any, List

class RuleEngine:
    def __init__(self, repository=None):
        self.repository = repository
        # Tracking variables for Protocol 3 (Ghost Focus) and Protocol 4 (Rewriting History)
        self.consecutive_idle_seconds = 0
        self.uncertain_session_ids = []

    def evaluate_rules(self, 
                       window_title: str, 
                       primary_category: str,
                       input_density: int, 
                       scroll_velocity: float, 
                       duration_seconds: float = 60.0,
                       recent_process: str = "") -> Tuple[str, float, bool]:
        """
        Evaluates the 4 Loophole Resolution Protocols.
        Returns:
            Tuple[str, float, bool]: (calculated_state, risk_score_override, override_triggered)
        """
        title_lower = window_title.lower()
        
        # --- Protocol 1: The DSA Pondering Exception ---
        ponder_keywords = ["leetcode", "github", "docs", "coursework", "tutorial", "arxiv", "stackoverflow"]
        is_ponder_window = any(kw in title_lower for kw in ponder_keywords)
        
        if is_ponder_window and input_density <= 2 and scroll_velocity <= 5.0:
            # Pondering: set state, no risk penalty, override triggered
            return "Pondering", 0.15, True

        # --- Protocol 2: The Comic / Manga Consumer Loophole ---
        comic_keywords = ["chapter", "manga", "comic", "scan", "feed", "facebook", "twitter", "reddit"]
        is_comic_window = any(kw in title_lower for kw in comic_keywords)
        
        if is_comic_window and input_density <= 5 and scroll_velocity > 40.0:
            # Comic Loophole: high scroll, low inputs -> Passive Leisure + high risk score
            return "Passive Leisure", 0.85, True

        # --- Protocol 3: The Ghost Focus / Left the Desk Catch ---
        # If input_density == 0 and scroll_velocity == 0 in a Core Tool, count time.
        if primary_category == "Core_Tool" and input_density == 0 and scroll_velocity == 0:
            self.consecutive_idle_seconds += int(duration_seconds)
            if self.consecutive_idle_seconds > 180: # > 3 minutes
                return "Idle_Away", 0.0, True
        else:
            # Reset consecutive idle timer if user did something
            if input_density > 0 or scroll_velocity > 0:
                self.consecutive_idle_seconds = 0

        # --- Protocol 4: Rewriting History (Retroactive State Correction) ---
        # This will be processed outside or triggered when input transitions from idle to active.
        # We can implement a trigger hook here if we have a repository connection:
        if self.repository is not None:
            self._handle_retroactive_history_rewrite(primary_category, input_density)

        return "", 0.0, False

    def _handle_retroactive_history_rewrite(self, current_category: str, input_density: int):
        """
        Inspect recent database sessions and check if we can rewrite uncertain states.
        If we find sessions labeled 'Pondering' or 'Idle_Away' which were uncertain, 
        and the user suddenly does high input in a Core_Tool, we rewrite them to 'Deep Work'.
        """
        # Let's say we track uncertain sessions. A session is uncertain if calculated_state was 'Pondering' but user input was 0.
        # Branch A: User resumes typing with I_D > 20 inside a Core_Tool -> Rewrite last 5 minutes of records to 'Deep Work'.
        if current_category == "Core_Tool" and input_density > 20:
            # Check the last 5 sessions (approx 5 mins) and rewrite any 'Pondering' or 'Idle_Away' that were passive.
            recent_sessions = self.repository.get_all_sessions(limit=5)
            with self.repository.get_connection() as conn:
                cursor = conn.cursor()
                for sess in recent_sessions:
                    sess_id, start, end, proc, cat, scroll, density, select, state, risk = sess
                    if state in ["Pondering", "Idle_Away"] and density <= 2:
                        cursor.execute("""
                        UPDATE behavioral_sessions
                        SET calculated_state = 'Deep Work', attention_risk_score = 0.0
                        WHERE id = ?
                        """, (sess_id,))
                conn.commit()
        # Branch B: User transitions to Leisure or system goes idle (input_density == 0) -> rewrite to 'Idle_Away'
        elif current_category == "Leisure":
            recent_sessions = self.repository.get_all_sessions(limit=5)
            with self.repository.get_connection() as conn:
                cursor = conn.cursor()
                for sess in recent_sessions:
                    sess_id, start, end, proc, cat, scroll, density, select, state, risk = sess
                    if state == "Pondering" and density <= 1:
                        cursor.execute("""
                        UPDATE behavioral_sessions
                        SET calculated_state = 'Idle_Away', attention_risk_score = 0.9
                        WHERE id = ?
                        """, (sess_id,))
                conn.commit()
