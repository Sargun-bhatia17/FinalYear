"""
ml_model.py
-----------
Wraps sklearn RandomForestClassifier behind a clean, version-stable public API.

Design rules (enforced):
  - The sklearn object is NEVER exposed externally; callers interact only through
    predict(), is_trained(), and load().
  - predict() raises ModelNotTrainedError when called before any model is loaded,
    rather than silently returning a garbage result.
  - File I/O uses an atomic swap (.tmp.joblib → .joblib via os.replace) so a crash
    mid-save never leaves a corrupted model on disk.
  - Zero time.sleep() — the class itself has no blocking calls.
  - logging module only; no print() statements.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from backend.repository.models import ModelNotTrainedError

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Canonical state labels — order must match the integer class IDs used in training.
STATE_LABELS: list[str] = [
    "Deep_Work",
    "Pondering",
    "Passive_Leisure",
    "Idle_Away",
]

# Risk weight per class: how much does each predicted class contribute to attention risk?
# Deep_Work = 0.0, Pondering = 0.15, Passive_Leisure = 1.0, Idle_Away = 0.5
_RISK_WEIGHTS: dict[str, float] = {
    "Deep_Work":       0.0,
    "Pondering":       0.15,
    "Passive_Leisure": 1.0,
    "Idle_Away":       0.5,
    "Active_Meeting":  0.0,
    "Unknown":         0.5,
}


class AttentionClassifier:
    """
    Wraps a RandomForestClassifier(n_estimators=100, class_weight='balanced').

    Public API
    ----------
    predict(feature_vector: np.ndarray) -> tuple[str, float]
        Returns (predicted_state, risk_score). Raises ModelNotTrainedError if untrained.
    is_trained() -> bool
        True if a fitted model is resident in memory.
    load(path: Path) -> None
        Loads a .joblib file from disk into memory.
    retrain(X, y) -> None
        Fits a new model, atomic-swaps the .joblib file, then hot-swaps in memory.
    """

    def __init__(self, model_path: Optional[Path] = None) -> None:
        if model_path is None:
            # Default location: AttentionLens/models/attention_classifier.joblib
            base_dir = Path(__file__).resolve().parent.parent.parent
            self._model_path: Path = base_dir / "models" / "attention_classifier.joblib"
        else:
            self._model_path = Path(model_path)

        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        self._model: Optional[RandomForestClassifier] = None

        # Try to load an existing model; stay untrained if none exists yet.
        if self._model_path.exists():
            try:
                self._load_from_disk(self._model_path)
                logger.info("AttentionClassifier loaded from %s", self._model_path)
            except Exception as exc:
                logger.warning("Could not load existing model — starting untrained: %s", exc)

    # ── Public interface ───────────────────────────────────────────────────────

    def is_trained(self) -> bool:
        """Returns True if a fitted model is resident in memory."""
        return self._model is not None

    def predict(self, feature_vector: np.ndarray) -> tuple[str, float]:
        """
        Predict the attention state and risk score for a single feature vector.

        Args:
            feature_vector: 1-D numpy array with shape (5,) containing
                            [interaction_density, scroll_velocity, context_entropy,
                             core_tool_ratio, time_of_day].

        Returns:
            (predicted_state, risk_score) where risk_score ∈ [0.0, 1.0].

        Raises:
            ModelNotTrainedError: If no fitted model is loaded.
        """
        if self._model is None:
            raise ModelNotTrainedError(
                "AttentionClassifier.predict() called before any model was loaded. "
                "Either wait for the retraining daemon or provide a pre-trained .joblib file."
            )

        x = feature_vector.reshape(1, -1)
        probs: np.ndarray = self._model.predict_proba(x)[0]

        # Map predicted class index → state label
        pred_class_idx: int = int(np.argmax(probs))
        raw_class = self._model.classes_[pred_class_idx]
        predicted_state = self._map_class_to_label(raw_class)

        # Risk score: probability-weighted sum of risk weights per class
        risk_score = self._compute_risk(probs)

        return predicted_state, float(np.clip(risk_score, 0.0, 1.0))

    def load(self, path: Path) -> None:
        """
        Loads a .joblib file from disk and makes it the active model.

        Args:
            path: Absolute path to the .joblib file.

        Raises:
            FileNotFoundError: If path does not exist.
            Exception: Propagated from joblib on corrupted files.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        self._load_from_disk(path)
        logger.info("Model hot-swapped from %s", path)

    def retrain(self, X_train: np.ndarray, y_train: np.ndarray) -> None:
        """
        Fits a new RandomForest on the provided data and atomic-swaps the .joblib file.

        The swap sequence is:
            1. Fit new model in memory.
            2. Save to <path>.tmp.joblib.
            3. os.replace(.tmp.joblib, .joblib)  ← atomic on POSIX and Windows.
            4. Hot-swap self._model.

        Args:
            X_train: Feature matrix, shape (n_samples, 5).
            y_train: Integer class labels, shape (n_samples,).
        """
        new_model = RandomForestClassifier(
            n_estimators=100,
            class_weight="balanced",
            random_state=42,
        )
        new_model.fit(X_train, y_train)

        tmp_path = self._model_path.with_suffix(".tmp.joblib")
        joblib.dump(new_model, tmp_path)
        os.replace(tmp_path, self._model_path)   # atomic swap

        self._model = new_model
        logger.info(
            "Model retrained and saved — classes=%s path=%s",
            list(new_model.classes_), self._model_path,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _load_from_disk(self, path: Path) -> None:
        """Deserialize a .joblib file and store as the active model."""
        self._model = joblib.load(path)

    def _map_class_to_label(self, raw_class: int | str) -> str:
        """Convert a model class value to a VALID_STATES-compliant label."""
        if isinstance(raw_class, (int, np.integer)):
            idx = int(raw_class)
            if 0 <= idx < len(STATE_LABELS):
                return STATE_LABELS[idx]
            logger.warning("Unknown class index %d — falling back to Unknown", idx)
            return "Unknown"
        # String class — may be an old label format
        label = str(raw_class)
        # Normalise legacy labels (e.g. "Deep Work" → "Deep_Work")
        _legacy = {
            "Deep Work":      "Deep_Work",
            "Passive Leisure": "Passive_Leisure",
        }
        return _legacy.get(label, label)

    def _compute_risk(self, probs: np.ndarray) -> float:
        """
        Compute a continuous risk score from the full probability distribution.

        Each class probability is weighted by its risk contribution in _RISK_WEIGHTS.
        This produces a smoother signal than a hard argmax risk lookup.
        """
        risk = 0.0
        for idx, prob in enumerate(probs):
            raw_class = self._model.classes_[idx]  # type: ignore[union-attr]
            label = self._map_class_to_label(raw_class)
            risk += prob * _RISK_WEIGHTS.get(label, 0.5)
        return risk
