"""
tests/test_fusion_engine.py
---------------------------
Pytest suite for FusionEngine.

All external dependencies (DataRepository, AttentionClassifier, RuleEngine)
are replaced with MagicMock objects so the tests are fast, deterministic,
and require no filesystem access.

Test 1: Cold-start  — N < 50   → w_ml == 0.0, w_rule == 1.0
Test 2: Hard rule   — confidence == 1.0 → final_state must equal rule state
Test 3: Atomic swap — retrain() leaves no .tmp.joblib artifact on disk
"""

from __future__ import annotations

import os
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

from backend.repository.models import (
    DataQuality,
    FeatureVector,
    FusionResult,
    ModelNotTrainedError,
    RuleResult,
    VALID_STATES,
)
from backend.logic.fusion_engine import (
    FusionEngine,
    COLD_START_THRESHOLD,
    ML_WEIGHT_CAP,
    RULE_WEIGHT_FLOOR,
)
from backend.logic.ml_model import AttentionClassifier, STATE_LABELS


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_fv(**kwargs) -> FeatureVector:
    """Minimal FeatureVector for testing."""
    defaults = dict(
        timestamp=datetime(2026, 6, 27, 10, 0, 0),
        interaction_density=0.3,
        scroll_velocity=0.1,
        context_entropy=0.2,
        category_distance=0.0,
        core_tool_ratio=0.8,
        time_of_day=10.0,
        data_quality=DataQuality.FULL,
        raw_event_count=60,
    )
    defaults.update(kwargs)
    return FeatureVector(**defaults)


def _make_rule_result(
    *,
    fired_protocol: str | None = None,
    assigned_state: str = "Unknown",
    risk_score_override: float = 0.0,
    confidence: float = 0.0,
    reason: str = "test",
) -> RuleResult:
    return RuleResult(
        fired_protocol=fired_protocol,
        assigned_state=assigned_state,
        risk_score_override=risk_score_override,
        confidence=confidence,
        reason=reason,
    )


# ── Test 1: N < 50 → cold-start weights ───────────────────────────────────────

class TestColdStart:
    def test_cold_start_weights_when_n_below_threshold(self):
        """
        When repo.count_valid_sessions() returns N < COLD_START_THRESHOLD (50),
        w_ml must be exactly 0.0 and w_rule must be exactly 1.0.
        """
        mock_repo = MagicMock()
        mock_repo.count_valid_sessions.return_value = COLD_START_THRESHOLD - 1

        mock_rule_engine = MagicMock()
        mock_rule_engine.evaluate.return_value = _make_rule_result(
            assigned_state="Pondering", confidence=0.0, risk_score_override=0.15
        )

        mock_classifier = MagicMock()
        # Classifier must NOT be called when w_ml == 0.0
        mock_classifier._model = None

        engine = FusionEngine(
            repository=mock_repo,
            classifier=mock_classifier,
            rule_engine=mock_rule_engine,
        )

        result = engine.score(
            feature_vector=_make_fv(),
            window_title="VS Code",
            process_name="code.exe",
        )

        assert result.ml_weight  == 0.0
        assert result.rule_weight == 1.0
        assert isinstance(result, FusionResult)

    def test_cold_start_classifier_not_called(self):
        """Classifier.predict() must NOT be invoked during cold-start."""
        mock_repo = MagicMock()
        mock_repo.count_valid_sessions.return_value = 10

        mock_rule_engine = MagicMock()
        mock_rule_engine.evaluate.return_value = _make_rule_result(
            assigned_state="Idle_Away", confidence=0.0, risk_score_override=0.0
        )

        mock_classifier = MagicMock()
        mock_classifier._model = MagicMock()

        engine = FusionEngine(
            repository=mock_repo,
            classifier=mock_classifier,
            rule_engine=mock_rule_engine,
        )
        engine.score(_make_fv(), "Some Title", "some.exe")

        mock_classifier.predict.assert_not_called()

    def test_weight_formula_above_threshold(self):
        """
        w_ml = min(0.8, N/500) when N >= 50.
        At N=250: w_ml = 0.5, w_rule = max(0.2, 0.5) = 0.5.
        """
        w_ml, w_rule = FusionEngine._compute_weights(250)
        assert w_ml   == pytest.approx(0.5)
        assert w_rule == pytest.approx(0.5)

    def test_weight_formula_at_cap(self):
        """At N=500+: w_ml is capped at ML_WEIGHT_CAP (0.8), w_rule = 0.2."""
        w_ml, w_rule = FusionEngine._compute_weights(1000)
        assert w_ml   == pytest.approx(ML_WEIGHT_CAP)
        assert w_rule == pytest.approx(RULE_WEIGHT_FLOOR)


# ── Test 2: confidence == 1.0 → hard rule overrides ML state ──────────────────

class TestHardRuleOverride:
    def test_hard_rule_final_state_overrides_ml(self):
        """
        When rule_result.confidence == 1.0, final_state MUST equal
        rule_result.assigned_state regardless of what the ML classifier predicts.
        """
        mock_repo = MagicMock()
        mock_repo.count_valid_sessions.return_value = 500  # above threshold

        # ML says "Deep_Work"
        mock_classifier = MagicMock()
        mock_classifier.predict.return_value = ("Deep_Work", 0.05)
        mock_classifier._model = MagicMock()
        mock_classifier._model.predict_proba.return_value = np.array([[0.9, 0.05, 0.03, 0.02]])

        # Hard rule fires: P5 → Active_Meeting, confidence=1.0
        mock_rule_engine = MagicMock()
        mock_rule_engine.evaluate.return_value = _make_rule_result(
            fired_protocol="P5_MEETING",
            assigned_state="Active_Meeting",
            risk_score_override=0.1,
            confidence=1.0,
            reason="Zoom detected",
        )

        engine = FusionEngine(
            repository=mock_repo,
            classifier=mock_classifier,
            rule_engine=mock_rule_engine,
        )

        result = engine.score(
            feature_vector=_make_fv(),
            window_title="Zoom Meeting",
            process_name="zoom.exe",
        )

        assert result.final_state == "Active_Meeting", (
            "Hard rule (confidence=1.0) must override ML state. "
            f"Got: {result.final_state!r}"
        )
        assert result.final_state in VALID_STATES

    def test_hard_rule_ml_still_influences_risk(self):
        """With a hard rule, ML risk is still blended into final_risk."""
        mock_repo = MagicMock()
        mock_repo.count_valid_sessions.return_value = 500

        ml_risk = 0.6
        mock_classifier = MagicMock()
        mock_classifier.predict.return_value = ("Passive_Leisure", ml_risk)
        mock_classifier._model = MagicMock()
        mock_classifier._model.predict_proba.return_value = np.array([[0.0, 0.0, 0.9, 0.1]])

        rule_risk = 0.1
        mock_rule_engine = MagicMock()
        mock_rule_engine.evaluate.return_value = _make_rule_result(
            fired_protocol="P5_MEETING",
            assigned_state="Active_Meeting",
            risk_score_override=rule_risk,
            confidence=1.0,
        )

        engine = FusionEngine(
            repository=mock_repo,
            classifier=mock_classifier,
            rule_engine=mock_rule_engine,
        )
        result = engine.score(_make_fv(), "Zoom", "zoom.exe")

        # Risk must be a blend — not simply rule_risk alone
        # w_ml = min(0.8, 500/500) = 0.8; w_rule = 0.2
        expected_risk = round(rule_risk * 0.2 + ml_risk * 0.8, 6)
        assert result.final_risk == pytest.approx(expected_risk, abs=0.01)
        assert 0.0 <= result.final_risk <= 1.0

    def test_soft_rule_ml_drives_state(self):
        """When confidence < 1.0, ML drives final_state (above cold-start)."""
        mock_repo = MagicMock()
        mock_repo.count_valid_sessions.return_value = 500

        mock_classifier = MagicMock()
        mock_classifier.predict.return_value = ("Deep_Work", 0.1)
        mock_classifier._model = MagicMock()
        mock_classifier._model.predict_proba.return_value = np.array([[0.9, 0.05, 0.03, 0.02]])

        mock_rule_engine = MagicMock()
        mock_rule_engine.evaluate.return_value = _make_rule_result(
            fired_protocol=None,
            assigned_state="Unknown",
            risk_score_override=0.0,
            confidence=0.0,
        )

        engine = FusionEngine(
            repository=mock_repo,
            classifier=mock_classifier,
            rule_engine=mock_rule_engine,
        )
        result = engine.score(_make_fv(), "VS Code", "code.exe")

        assert result.final_state == "Deep_Work"


# ── Test 3: Atomic swap verification ──────────────────────────────────────────

class TestAtomicSwap:
    def test_retrain_deletes_tmp_joblib(self):
        """
        After AttentionClassifier.retrain() completes, the .tmp.joblib file must
        not exist on disk (it must have been atomically renamed to .joblib).

        This validates the atomic swap contract:
            1. Save to <path>.tmp.joblib
            2. os.replace(.tmp.joblib, .joblib)   ← .tmp.joblib no longer exists
            3. Hot-swap self._model
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / "attention_classifier.joblib"
            tmp_model_path = model_path.with_suffix(".tmp.joblib")

            # Build a tiny training set — 4 classes, 8 samples
            X = np.array([
                [0.5, 0.0, 0.0, 1.0, 10.0],
                [0.4, 0.1, 0.1, 0.9, 14.0],
                [0.02, 0.02, 0.0, 1.0, 11.0],
                [0.01, 0.01, 0.1, 0.9, 9.0],
                [0.01, 0.8, 0.2, 0.0, 15.0],
                [0.02, 0.9, 0.3, 0.0, 16.0],
                [0.0, 0.0, 0.0, 0.0, 17.0],
                [0.0, 0.0, 0.0, 0.0, 20.0],
            ], dtype=np.float32)
            y = np.array([0, 0, 1, 1, 2, 2, 3, 3], dtype=np.int32)

            classifier = AttentionClassifier(model_path=model_path)
            classifier.retrain(X, y)

            # The .tmp.joblib must be gone after successful retrain
            assert not tmp_model_path.exists(), (
                f"Atomic swap failed: {tmp_model_path.name} still exists after retrain(). "
                "os.replace() must delete the .tmp file."
            )

            # The final .joblib must exist
            assert model_path.exists(), (
                f"{model_path.name} not found after retrain() — save failed."
            )

    def test_retrain_model_is_loaded_in_memory(self):
        """After retrain(), the classifier's in-memory model must be updated."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / "attention_classifier.joblib"
            X = np.array([[0.5, 0.0, 0.0, 1.0, 10.0], [0.0, 0.0, 0.0, 0.0, 20.0]], dtype=np.float32)
            y = np.array([0, 3], dtype=np.int32)

            classifier = AttentionClassifier(model_path=model_path)
            assert not classifier.is_trained()

            classifier.retrain(X, y)
            assert classifier.is_trained()

    def test_predict_raises_before_trained(self):
        """predict() must raise ModelNotTrainedError when no model is loaded."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / "fresh_classifier.joblib"
            classifier = AttentionClassifier(model_path=model_path)
            assert not classifier.is_trained()

            with pytest.raises(ModelNotTrainedError):
                classifier.predict(np.array([0.1, 0.2, 0.3, 0.4, 12.0], dtype=np.float32))
