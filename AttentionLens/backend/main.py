import datetime
import logging
import time

from backend.config.settings import settings
from backend.repository.repository import DataRepository
from backend.repository.models import SessionRecord, VALID_STATES
from backend.logic.rule_engine import PONDERING_SOFT_ALERT_MIN
from backend.tracker.tracker import Tracker, RawEventSnapshot
from backend.logic.behavior_engine import (
    calculate_interaction_density,
    calculate_scroll_velocity,
    calculate_context_entropy,
)
from backend.logic.rule_engine import RuleEngine
from backend.logic.feature_engineer import FeatureEngineer
from backend.logic.ml_model import AttentionClassifier
from backend.logic.retraining_daemon import RetrainingDaemon
from backend.logic.fusion_engine import FusionEngine
from backend.server.api_server import ApiServer
from backend.utils.lifecycle import ShutdownCoordinator

logger = logging.getLogger(__name__)


class MainApp:
    def __init__(self):
        logger.info("Initializing AttentionLens Backend Engine...")

        self.repository = DataRepository()

        self.rule_engine = RuleEngine(self.repository)
        self.feature_engineer = FeatureEngineer(self.repository)
        self.classifier = AttentionClassifier()
        self.fusion_engine = FusionEngine(self.repository)

        self.retraining_daemon = RetrainingDaemon(self.repository, self.classifier)
        self.api_server = ApiServer(repository=self.repository, port=settings.api_port)

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
        self.pondering_streak_minutes: int = 0

    def start(self):
        self.tracker.start()
        self.retraining_daemon.start()
        self.api_server.start()

        # Register signal handlers for graceful shutdown
        coordinator = ShutdownCoordinator(
            tracker=self.tracker,
            retraining_daemon=self.retraining_daemon,
            api_server=self.api_server,
            repository=self.repository,
        )
        coordinator.register()

        logger.info("AttentionLens background threads started successfully.")

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
            logger.warning("Failed to seed initial state: %s", e)

        try:
            self.run_loop()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        logger.info("Shutting down AttentionLens backend...")
        self.tracker.stop()
        self.retraining_daemon.stop()
        self.api_server.stop()
        logger.info("Shutdown complete.")


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

        # Convert buffer to list of RawEvent typed dicts for the calculators
        events = []
        for i, e in enumerate(buffer):
            # Estimate timestamp for each 5-second event in the buffer
            t_offset = (len(buffer) - 1 - i) * 5
            ev_time = end_time - datetime.timedelta(seconds=t_offset)
            events.append({
                "id": i,
                "timestamp": ev_time.strftime("%Y-%m-%d %H:%M:%S"),
                "process_name": e["process"],
                "window_title": e["title"],
                "keystroke_count": e["keystrokes"],
                "mouse_click_count": e["clicks"],
                "scroll_delta_y": e["scroll_y"],
            })

        taxonomy_snapshot = self.repository.get_taxonomy_snapshot()
        primary_category = taxonomy_snapshot.get(primary_proc.lower(), "Supporting_Tool")

        input_density = calculate_interaction_density(events)
        scroll_velocity = calculate_scroll_velocity(events)
        entropy = calculate_context_entropy(events, taxonomy_snapshot)

        total_keystrokes = sum(e["keystrokes"] for e in buffer)
        total_clicks = sum(e["clicks"] for e in buffer)
        total_scroll = sum(e["scroll_y"] for e in buffer)

        raw_input_density = total_keystrokes + total_clicks
        raw_scroll_velocity = abs(total_scroll) / 60.0
        has_selection = total_clicks > 15

        primary_title = buffer[0]["title"]
        feat_vector = self.feature_engineer.build_feature_vector()

        # Gather pending unknown session context for P3/P4
        pending_sessions = self.repository.get_pending_unknown_sessions()
        pending_queue_length = len(pending_sessions)
        pending_duration_s = 0.0
        if pending_sessions:
            try:
                oldest_ts = pending_sessions[0]["start_time"]
                oldest_dt = datetime.datetime.strptime(oldest_ts, "%Y-%m-%d %H:%M:%S")
                pending_duration_s = (datetime.datetime.now() - oldest_dt).total_seconds()
            except Exception:
                pending_duration_s = 0.0

        rule_result = self.rule_engine.evaluate(
            feature_vector=feat_vector,
            window_title=primary_title,
            process_name=primary_proc,
            pending_unknown_duration_s=pending_duration_s,
            pending_queue_length=pending_queue_length,
            most_recent_category=primary_category,
        )
        rule_override = rule_result.fired_protocol is not None
        rule_state = rule_result.assigned_state
        rule_risk  = rule_result.risk_score_override

        # Sync pondering streak from rule engine stateful context
        self.pondering_streak_minutes = self.rule_engine.pondering_streak_minutes

        import numpy as np
        classifier_input = np.array([
            feat_vector.interaction_density,
            feat_vector.scroll_velocity,
            feat_vector.context_entropy,
            feat_vector.core_tool_ratio,
            feat_vector.time_of_day
        ], dtype=np.float32)

        ml_state, ml_risk = self.classifier.predict(classifier_input)

        final_state, final_risk = self.fusion_engine.fuse_scores(
            ml_predicted_state=ml_state,
            ml_risk_score=ml_risk,
            rule_state=rule_state,
            rule_risk_score=rule_risk,
            rule_override_triggered=rule_override,
        )

        # Ensure final state is VALID_STATES-compliant; fall back to Unknown
        if final_state not in VALID_STATES:
            final_state = "Unknown"

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

        # Pondering soft alert — fires once when streak reaches threshold
        if (self.rule_engine.soft_alert_triggered
                and self.pondering_streak_minutes >= PONDERING_SOFT_ALERT_MIN):
            pondering_alert = {
                "alert_trigger": "Pondering_Depth_Threshold",
                "primary_cause": (
                    f"You have been in deep analysis for "
                    f"{self.pondering_streak_minutes} continuous minutes."
                ),
                "actionable_prompt": (
                    "This appears to be intentional problem-solving. "
                    "Remember to stretch if you are stuck."
                ),
                "suggested_action": "Acknowledge",
            }
            self.api_server.trigger_alert(pondering_alert)
            # Reset flag so the alert doesn't fire every minute after threshold
            self.rule_engine.soft_alert_triggered = False

        self.api_server.update_state("attention_score",   final_risk)
        self.api_server.update_state("calculated_state",  final_state)
        self.api_server.update_state("active_category",   primary_category)
        self.api_server.update_state("active_process",    primary_proc)
        self.api_server.update_state("active_title",       primary_title)
        self.api_server.update_state("fired_protocol",    rule_result.fired_protocol)
        self.api_server.update_state("data_quality",      feat_vector.data_quality.value)

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
            logger.error("Failed to update dashboard history list: %s", e)


if __name__ == "__main__":
    from backend.utils.logger import configure_logging
    configure_logging(
        level=settings.log_level,
        max_bytes=settings.log_max_bytes,
        backup_count=settings.log_backup_count,
    )
    app = MainApp()
    app.start()
