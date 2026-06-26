import datetime
import time

from backend.repository.repository import DataRepository
from backend.repository.models import SessionRecord
from backend.tracker.tracker import Tracker, RawEventSnapshot
from backend.logic.behavior_engine import BehaviorEngine
from backend.logic.rule_engine import RuleEngine
from backend.logic.feature_engineer import FeatureEngineer
from backend.logic.ml_model import AttentionClassifier
from backend.logic.retraining_daemon import RetrainingDaemon
from backend.logic.fusion_engine import FusionEngine
from backend.server.api_server import ApiServer


class MainApp:
    def __init__(self):
        print("Initializing AttentionLens Backend Engine...")

        self.repository = DataRepository()

        self.behavior_engine = BehaviorEngine()
        self.rule_engine = RuleEngine(self.repository)
        self.feature_engineer = FeatureEngineer(self.repository)
        self.classifier = AttentionClassifier()
        self.fusion_engine = FusionEngine(self.repository)

        self.retraining_daemon = RetrainingDaemon(self.repository, self.classifier)
        self.api_server = ApiServer(port=8421)

        self.tracker = Tracker(
            repository=self.repository,
            on_flush=self._on_raw_event,
        )
        self.poll_interval = self.tracker.flush_interval
        self.session_interval = self.tracker.session_interval
        self.polling_per_session = int(self.session_interval / self.poll_interval)

        self.session_start_time = datetime.datetime.now()
        self.poll_count = 0
        self.window_events_buffer: list[dict] = []
        self.consecutive_high_risk_sessions = 0

    def start(self):
        self.tracker.start()
        self.retraining_daemon.start()
        self.api_server.start()

        print("AttentionLens background threads started successfully.")

        try:
            recent = self.repository.get_all_sessions(limit=15)
            recent_tuples = [
                (
                    s["id"],
                    s["start_time"],
                    s["end_time"],
                    s["primary_process"],
                    s["primary_category"],
                    s["scroll_velocity"],
                    s["input_density"],
                    s["has_text_selection"],
                    s["calculated_state"],
                    s["attention_risk_score"],
                )
                for s in recent
            ]
            self.api_server.update_state("recent_sessions", recent_tuples)
            self.api_server.update_state("session_count", self.repository.get_session_count())
        except Exception as e:
            print(f"Failed to seed initial state: {e}")

        try:
            self.run_loop()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        print("Shutting down AttentionLens backend...")
        self.tracker.stop()
        self.retraining_daemon.stop()
        self.api_server.stop()
        print("Shutdown complete.")

    def _on_raw_event(self, snapshot: RawEventSnapshot) -> None:
        """Called by Tracker every flush_interval seconds."""
        self.window_events_buffer.append({
            "process": snapshot.process,
            "title": snapshot.title,
            "keystrokes": snapshot.keys,
            "clicks": snapshot.clicks,
            "scroll_y": snapshot.scrolls,
        })
        self.poll_count += 1

        self.api_server.update_state("active_process", snapshot.process)
        self.api_server.update_state("active_title", snapshot.title)
        self.api_server.update_state("tracker_status", self.tracker.health())

        if self.poll_count >= self.polling_per_session:
            session_end_time = datetime.datetime.now()
            self.process_minute_session(
                self.session_start_time, session_end_time, self.window_events_buffer
            )
            self.window_events_buffer = []
            self.poll_count = 0
            self.session_start_time = session_end_time

    def run_loop(self):
        """Keep the main thread alive; 5s flushes run inside Tracker."""
        while True:
            time.sleep(1)

    def process_minute_session(self, start_time, end_time, buffer):
        """Processes the 60-second window events, calculates risk, and writes session to DB."""
        if not buffer:
            return

        process_counts = {}
        for event in buffer:
            p = event["process"]
            process_counts[p] = process_counts.get(p, 0) + 1
        primary_proc = max(process_counts, key=process_counts.get)

        taxonomy = self.repository.get_taxonomy()
        primary_category, _ = taxonomy.get(primary_proc.lower(), ("Supporting_Tool", 1.0))

        total_keystrokes = sum(e["keystrokes"] for e in buffer)
        total_clicks = sum(e["clicks"] for e in buffer)
        total_scroll = sum(e["scroll_y"] for e in buffer)

        input_density = self.behavior_engine.calculate_interaction_density(
            total_keystrokes, total_clicks
        )
        scroll_velocity = self.behavior_engine.calculate_scroll_velocity(
            total_scroll, duration_seconds=60.0
        )

        has_selection = total_clicks > 15

        categories = []
        for e in buffer:
            cat, _ = taxonomy.get(e["process"].lower(), ("Supporting_Tool", 1.0))
            categories.append(cat)
        entropy = self.behavior_engine.calculate_context_switching_entropy(categories)

        primary_title = buffer[0]["title"]
        rule_state, rule_risk, rule_override = self.rule_engine.evaluate_rules(
            window_title=primary_title,
            primary_category=primary_category,
            input_density=input_density,
            scroll_velocity=scroll_velocity,
            duration_seconds=60.0,
            recent_process=primary_proc,
        )

        feat_vector, _ = self.feature_engineer.build_feature_vector(
            current_input_density=input_density,
            current_scroll_velocity=scroll_velocity,
            current_entropy=entropy,
            current_category=primary_category,
        )

        ml_state, ml_risk = self.classifier.predict(feat_vector)

        final_state, final_risk = self.fusion_engine.fuse_scores(
            ml_predicted_state=ml_state,
            ml_risk_score=ml_risk,
            rule_state=rule_state,
            rule_risk_score=rule_risk,
            rule_override_triggered=rule_override,
        )

        try:
            session_rec = SessionRecord(
                start_time=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=end_time.strftime("%Y-%m-%d %H:%M:%S"),
                primary_process=primary_proc,
                primary_category=primary_category,
                scroll_velocity=scroll_velocity,
                input_density=input_density,
                has_text_selection=has_selection,
                calculated_state=final_state,
                attention_risk_score=final_risk,
            )
            self.repository.insert_session(session_rec)
        except Exception as e:
            print(f"Failed to insert behavioral session: {e}")

        if final_risk > 0.75:
            self.consecutive_high_risk_sessions += 1
            if self.consecutive_high_risk_sessions >= 3:
                alert = {
                    "alert_trigger": "Attention_Fragmentation_High",
                    "primary_cause": (
                        f"Frequent context switching or leisure activity detected "
                        f"inside '{primary_proc}' over the last 3 minutes."
                    ),
                    "actionable_prompt": (
                        f"Your attention pattern is currently breaking up in {primary_proc}. "
                        "Consider minimizing distracting tabs. It typically takes 3 minutes "
                        "of quiet work to re-enter deep focus."
                    ),
                    "suggested_action": "Minimize Distracting Processes",
                }
                self.api_server.trigger_alert(alert)
        else:
            self.consecutive_high_risk_sessions = 0
            self.api_server.update_state("current_alert", None)

        self.api_server.update_state("attention_score", final_risk)
        self.api_server.update_state("calculated_state", final_state)
        self.api_server.update_state("active_category", primary_category)

        try:
            recent = self.repository.get_all_sessions(limit=15)
            recent_tuples = [
                (
                    s["id"],
                    s["start_time"],
                    s["end_time"],
                    s["primary_process"],
                    s["primary_category"],
                    s["scroll_velocity"],
                    s["input_density"],
                    s["has_text_selection"],
                    s["calculated_state"],
                    s["attention_risk_score"],
                )
                for s in recent
            ]
            self.api_server.update_state("recent_sessions", recent_tuples)
            self.api_server.update_state("session_count", self.repository.get_session_count())
        except Exception as e:
            print(f"Failed to update dashboard history list: {e}")


if __name__ == "__main__":
    app = MainApp()
    app.start()
