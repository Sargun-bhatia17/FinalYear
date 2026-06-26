import time
import datetime
import random
from repository.activity_repository import ActivityRepository
from tracker.window_hook import WindowHook
from tracker.input_listener import InputListener
from logic.behavior_engine import BehaviorEngine
from logic.rule_engine import RuleEngine
from logic.feature_engineer import FeatureEngineer
from logic.ml_model import AttentionClassifier
from logic.retraining_daemon import RetrainingDaemon
from logic.fusion_engine import FusionEngine
from server.api_server import ApiServer

class MainApp:
    def __init__(self):
        print("Initializing AttentionLens Backend Engine...")
        
        # 1. Initialize DB Repository
        self.repository = ActivityRepository()
        
        # 2. Initialize low-level hooks
        self.window_hook = WindowHook()
        self.input_listener = InputListener()
        
        # 3. Initialize logic modules
        self.behavior_engine = BehaviorEngine()
        self.rule_engine = RuleEngine(self.repository)
        self.feature_engineer = FeatureEngineer(self.repository)
        self.classifier = AttentionClassifier()
        self.fusion_engine = FusionEngine(self.repository)
        
        # 4. Start background daemons & servers
        self.retraining_daemon = RetrainingDaemon(self.repository, self.classifier)
        self.api_server = ApiServer(port=8421)
        
        # Accumulators for 5-second polling inside the 60-second window
        self.poll_interval = 5.0
        self.session_interval = 60.0
        self.polling_per_session = int(self.session_interval / self.poll_interval)
        
        # Alert tracking
        self.consecutive_high_risk_sessions = 0

    def start(self):
        # Start input hooks
        self.input_listener.start()
        
        # Start retraining daemon
        self.retraining_daemon.start()
        
        # Start Websocket IPC Server
        self.api_server.start()
        
        print("AttentionLens background threads started successfully.")
        
        # Seed initial session count to client
        self.api_server.update_state("session_count", self.repository.get_session_count())
        
        try:
            self.run_loop()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        print("Shutting down AttentionLens backend...")
        self.input_listener.stop()
        self.retraining_daemon.stop()
        self.api_server.stop()
        print("Shutdown complete.")

    def run_loop(self):
        session_start_time = datetime.datetime.now()
        poll_count = 0
        
        # Cache of current minute window properties
        window_events_buffer = []
        
        while True:
            loop_start = time.time()
            
            # --- 5-Second Active Window Polling ---
            proc_name, win_title = self.window_hook.get_active_window()
            keystrokes, clicks, scroll_y = self.input_listener.get_and_reset_deltas()
            
            # Record raw event
            try:
                self.repository.insert_raw_window_event(proc_name, win_title, keystrokes, clicks, scroll_y)
            except Exception as e:
                print(f"Failed to insert raw event: {e}")
                
            # Add to memory buffer for this session
            window_events_buffer.append({
                "process": proc_name,
                "title": win_title,
                "keystrokes": keystrokes,
                "clicks": clicks,
                "scroll_y": scroll_y
            })
            
            poll_count += 1
            
            # Send real-time telemetry to client every 5 seconds
            self.api_server.update_state("active_process", proc_name)
            self.api_server.update_state("active_title", win_title)
            
            # Check if 60 seconds (12 polls of 5 seconds) has elapsed
            if poll_count >= self.polling_per_session:
                session_end_time = datetime.datetime.now()
                
                # --- 60-Second Behavioral Aggregation ---
                self.process_minute_session(session_start_time, session_end_time, window_events_buffer)
                
                # Reset accumulators for next session
                window_events_buffer = []
                poll_count = 0
                session_start_time = session_end_time
                
            # Calculate sleep to maintain precisely 5-second polling interval
            elapsed = time.time() - loop_start
            sleep_time = max(0.1, self.poll_interval - elapsed)
            time.sleep(sleep_time)

    def process_minute_session(self, start_time, end_time, buffer):
        """Processes the 60-second window events, calculates risk, and writes session to DB."""
        if not buffer:
            return
            
        # 1. Determine Primary Process & Category
        process_counts = {}
        for event in buffer:
            p = event["process"]
            process_counts[p] = process_counts.get(p, 0) + 1
        primary_proc = max(process_counts, key=process_counts.get)
        
        # Resolve category from taxonomy DB
        taxonomy = self.repository.get_taxonomy()
        primary_category, _ = taxonomy.get(primary_proc.lower(), ("Supporting_Tool", 1.0))
        
        # 2. Run Behavioral Scoring Calculations
        total_keystrokes = sum(e["keystrokes"] for e in buffer)
        total_clicks = sum(e["clicks"] for e in buffer)
        total_scroll = sum(e["scroll_y"] for e in buffer)
        
        input_density = self.behavior_engine.calculate_interaction_density(total_keystrokes, total_clicks)
        scroll_velocity = self.behavior_engine.calculate_scroll_velocity(total_scroll, duration_seconds=60.0)
        
        # Check if user highlighted any text (mouse clicks in series or scroll changes)
        has_selection = total_clicks > 15  # Simplification for demo
        
        # Calculate Context Switching Entropy over this minute's event stream
        categories = []
        for e in buffer:
            cat, _ = taxonomy.get(e["process"].lower(), ("Supporting_Tool", 1.0))
            categories.append(cat)
        entropy = self.behavior_engine.calculate_context_switching_entropy(categories)
        
        # 3. Rule Engine overrides evaluation
        primary_title = buffer[0]["title"]  # Representative title
        rule_state, rule_risk, rule_override = self.rule_engine.evaluate_rules(
            window_title=primary_title,
            primary_category=primary_category,
            input_density=input_density,
            scroll_velocity=scroll_velocity,
            duration_seconds=60.0,
            recent_process=primary_proc
        )
        
        # 4. Feature Vector building & ML inference
        feat_vector, _ = self.feature_engineer.build_feature_vector(
            current_input_density=input_density,
            current_scroll_velocity=scroll_velocity,
            current_entropy=entropy,
            current_category=primary_category
        )
        
        ml_state, ml_risk = self.classifier.predict(feat_vector)
        
        # 5. Fusion Engine blending
        final_state, final_risk = self.fusion_engine.fuse_scores(
            ml_predicted_state=ml_state,
            ml_risk_score=ml_risk,
            rule_state=rule_state,
            rule_risk_score=rule_risk,
            rule_override_triggered=rule_override
        )
        
        # Save session to Database
        try:
            self.repository.insert_behavioral_session(
                start_time=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=end_time.strftime("%Y-%m-%d %H:%M:%S"),
                primary_process=primary_proc,
                primary_category=primary_category,
                scroll_velocity=scroll_velocity,
                input_density=input_density,
                has_selection=has_selection,
                calculated_state=final_state,
                risk_score=final_risk
            )
        except Exception as e:
            print(f"Failed to insert behavioral session: {e}")
            
        # 6. Actionable Recommendation Alert check
        # Risk score > 0.75 continuously for 3 minutes (3 consecutive sessions)
        if final_risk > 0.75:
            self.consecutive_high_risk_sessions += 1
            if self.consecutive_high_risk_sessions >= 3:
                alert = {
                    "alert_trigger": "Attention_Fragmentation_High",
                    "primary_cause": f"Frequent context switching or leisure activity detected inside '{primary_proc}' over the last 3 minutes.",
                    "actionable_prompt": f"Your attention pattern is currently breaking up in {primary_proc}. Consider minimizing distracting tabs. It typically takes 3 minutes of quiet work to re-enter deep focus.",
                    "suggested_action": "Minimize Distracting Processes"
                }
                self.api_server.trigger_alert(alert)
        else:
            self.consecutive_high_risk_sessions = 0
            self.api_server.update_state("current_alert", None)
            
        # Update WebSockets UI state
        self.api_server.update_state("attention_score", final_risk)
        self.api_server.update_state("calculated_state", final_state)
        self.api_server.update_state("active_category", primary_category)
        
        # Retrieve recent sessions to populate timeline
        try:
            recent = self.repository.get_all_sessions(limit=15)
            self.api_server.update_state("recent_sessions", recent)
            self.api_server.update_state("session_count", self.repository.get_session_count())
        except Exception as e:
            print(f"Failed to update dashboard history list: {e}")

if __name__ == "__main__":
    app = MainApp()
    app.start()
