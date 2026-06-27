"""
retraining_daemon.py
--------------------
Background thread that periodically checks whether the classifier needs retraining
and, if so, runs a safe retrain cycle.

Design rules (enforced):
  - threading.Thread(daemon=True) — never blocks shutdown.
  - run() waits via threading.Event.wait(timeout=60). Zero time.sleep() calls.
  - _safe_retrain() wraps the entire retrain pipeline in try/except Exception so
    a single bad cycle never kills the daemon loop.
  - Retraining is skipped when fewer than COLD_START_THRESHOLD valid sessions exist.
  - Feature matrix is assembled from the DB; target labels are integer class IDs.
  - After fitting: save ModelMetadata → metadata.json, then atomic swap .joblib.
  - Only classifier.load() (the public API) is called after the swap — the daemon
    never touches _model directly.
  - logging module only; no print() statements.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from backend.repository.models import ModelMetadata, RetriggerPolicy
from backend.logic.ml_model import STATE_LABELS

if TYPE_CHECKING:
    from backend.repository.repository import DataRepository
    from backend.logic.ml_model import AttentionClassifier

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

COLD_START_THRESHOLD: int = 50   # Minimum valid sessions before any training attempt


class RetrainingDaemon(threading.Thread):
    """
    Daemon thread that monitors session growth and retrains the classifier
    when RetriggerPolicy conditions are met.

    Args:
        repository:  DataRepository — used for data queries only.
        classifier:  AttentionClassifier — .retrain() and .load() are the only
                     methods called.
        policy:      RetriggerPolicy instance controlling thresholds.
        check_interval_s: How often (seconds) the policy is evaluated.
    """

    def __init__(
        self,
        repository: "DataRepository",
        classifier: "AttentionClassifier",
        policy: RetriggerPolicy | None = None,
        check_interval_s: int = 60,
    ) -> None:
        super().__init__(name="RetrainingDaemon", daemon=True)
        self._repo       = repository
        self._classifier = classifier
        self._policy     = policy or RetriggerPolicy()
        self._interval   = check_interval_s
        self._stop_event = threading.Event()

        self._last_trained_count: int = 0
        self._last_trained_at:    datetime = datetime.now(tz=timezone.utc)

    # ── Thread lifecycle ───────────────────────────────────────────────────────

    def run(self) -> None:
        """Main daemon loop — waits on an Event so shutdown is instantaneous."""
        logger.info("RetrainingDaemon started (interval=%ds)", self._interval)
        try:
            self._last_trained_count = self._repo.count_valid_sessions()
        except Exception as exc:
            logger.warning("Could not read initial session count: %s", exc)

        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._interval)
            if self._stop_event.is_set():
                break
            if self._should_retrain():
                self._safe_retrain()

        logger.info("RetrainingDaemon stopped.")

    def stop(self) -> None:
        """Signal the daemon to exit cleanly after the current sleep."""
        self._stop_event.set()

    # ── Policy check ───────────────────────────────────────────────────────────

    def _should_retrain(self) -> bool:
        """Return True if any RetriggerPolicy condition is satisfied."""
        try:
            current_count = self._repo.count_valid_sessions()
        except Exception as exc:
            logger.warning("count_valid_sessions() failed: %s", exc)
            return False

        new_rows  = current_count - self._last_trained_count
        days_old  = (datetime.now(tz=timezone.utc) - self._last_trained_at).days

        if new_rows >= self._policy.min_new_rows:
            logger.info("Retrain triggered: %d new valid rows.", new_rows)
            return True
        if days_old >= self._policy.max_days_since_training:
            logger.info("Retrain triggered: %d days since last training.", days_old)
            return True
        return False

    # ── Safe retrain wrapper ───────────────────────────────────────────────────

    def _safe_retrain(self) -> None:
        """
        Wrapper that catches all exceptions from the retrain pipeline.
        A crash here reschedules silently rather than killing the daemon.
        """
        try:
            self._retrain_pipeline()
            self._last_trained_count = self._repo.count_valid_sessions()
            self._last_trained_at    = datetime.now(tz=timezone.utc)
        except Exception as exc:
            logger.error("Retrain cycle failed — will retry next interval: %s", exc, exc_info=True)

    def _retrain_pipeline(self) -> None:
        """
        Full retrain cycle:
          1. Query valid sessions from DB.
          2. Abort if < COLD_START_THRESHOLD.
          3. Build feature matrix X and integer label vector y.
          4. 80/20 train/test split.
          5. Fit via classifier.retrain() (atomic .joblib swap happens inside).
          6. Evaluate per-class accuracy on the test split.
          7. Write ModelMetadata → metadata.json.
          8. Hot-swap via classifier.load().
        """
        sessions = self._repo.get_all_sessions(limit=5000)
        # Filter out Unknown/INSUFFICIENT quality rows
        valid = [s for s in sessions if s.get("calculated_state", "Unknown") != "Unknown"]

        if len(valid) < COLD_START_THRESHOLD:
            logger.info(
                "Retraining aborted — only %d valid sessions (threshold=%d).",
                len(valid), COLD_START_THRESHOLD,
            )
            return

        X, y = self._build_feature_matrix(valid)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y if len(set(y)) > 1 else None
        )

        # retrain() does atomic .joblib swap internally
        self._classifier.retrain(X_train, y_train)

        # Evaluate on held-out test set using the now-loaded model
        class_accuracies = self._evaluate(X_test, y_test)

        # Write metadata.json beside the .joblib file
        self._write_metadata(
            session_count=len(valid),
            class_accuracies=class_accuracies,
        )

        # Hot-swap: point classifier at the newly-written file
        self._classifier.load(self._classifier._model_path)
        logger.info(
            "Retraining complete — %d sessions, class accuracies: %s",
            len(valid), class_accuracies,
        )

    # ── Feature engineering for training ──────────────────────────────────────

    def _build_feature_matrix(
        self, sessions: list[dict]
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Convert DB session dicts into a numpy feature matrix and integer label vector.

        Features: [input_density, scroll_velocity, category_entropy_proxy,
                   core_tool_ratio_proxy, time_of_day]
        Labels:   Integer indices into STATE_LABELS.
        """
        X_rows: list[list[float]] = []
        y_labels: list[int] = []

        label_to_int = {label: idx for idx, label in enumerate(STATE_LABELS)}

        for sess in sessions:
            state = sess.get("calculated_state", "Unknown")
            label_int = label_to_int.get(state)
            if label_int is None:
                continue   # skip unrecognised states

            f0 = float(sess.get("input_density",    0.0))
            f1 = float(sess.get("scroll_velocity",  0.0))
            cat = sess.get("primary_category", "Supporting_Tool")
            f2 = {"Core_Tool": 0.0, "Supporting_Tool": 0.5, "Leisure": 1.0}.get(cat, 0.5)
            f3 = 1.0 if cat == "Core_Tool" else 0.0

            start_ts = sess.get("start_time", "")
            try:
                dt = datetime.strptime(start_ts, "%Y-%m-%d %H:%M:%S")
                f4 = dt.hour + (dt.minute / 60.0)
            except (ValueError, TypeError):
                f4 = 12.0

            X_rows.append([f0, f1, f2, f3, f4])
            y_labels.append(label_int)

        return np.array(X_rows, dtype=np.float32), np.array(y_labels, dtype=np.int32)

    def _evaluate(
        self, X_test: np.ndarray, y_test: np.ndarray
    ) -> dict[str, float]:
        """Compute per-class accuracy on the test split using the current model."""
        class_accuracies: dict[str, float] = {}
        try:
            for idx, label in enumerate(STATE_LABELS):
                mask = y_test == idx
                if not mask.any():
                    continue
                X_cls = X_test[mask]
                y_cls = y_test[mask]
                preds_raw = [self._classifier.predict(row)[0] for row in X_cls]
                preds_int = [
                    {l: i for i, l in enumerate(STATE_LABELS)}.get(p, -1)
                    for p in preds_raw
                ]
                acc = float(accuracy_score(y_cls, preds_int))
                class_accuracies[label] = round(acc, 4)
        except Exception as exc:
            logger.warning("Per-class evaluation failed: %s", exc)
        return class_accuracies

    def _write_metadata(
        self, session_count: int, class_accuracies: dict[str, float]
    ) -> None:
        """Serialise ModelMetadata to metadata.json beside the .joblib file."""
        metadata = ModelMetadata(
            trained_at=datetime.now(tz=timezone.utc),
            session_count=session_count,
            class_accuracies=class_accuracies,
        )
        meta_path = self._classifier._model_path.with_name("metadata.json")
        payload = {
            "trained_at":       metadata.trained_at.isoformat(),
            "session_count":    metadata.session_count,
            "class_accuracies": metadata.class_accuracies,
        }
        meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Wrote metadata.json → %s", meta_path)
