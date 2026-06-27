"""
fusion_engine.py
----------------
Blends ML and rule-engine signals into a single authoritative FusionResult.

Design rules (enforced):
  - All three dependencies (DataRepository, AttentionClassifier, RuleEngine) are
    injected in __init__; FusionEngine never constructs them itself.
  - Module-level constants only — no magic numbers inside methods.
  - If rule_result.confidence == 1.0, the rule state is the final state with no
    exception. ML may still influence final_risk, but NOT final_state.
  - Cold-start (N < COLD_START_THRESHOLD): w_ml = 0.0, w_rule = 1.0.
  - Weight formula:
      w_ml   = min(ML_WEIGHT_CAP, N / 500)  if N >= COLD_START_THRESHOLD else 0.0
      w_rule = max(RULE_WEIGHT_FLOOR, 1.0 - w_ml)
  - ModelNotTrainedError from the classifier is caught; treated as cold-start.
  - logging module only; no print() statements.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from backend.repository.models import (
    FeatureVector,
    FusionResult,
    ModelNotTrainedError,
    VALID_STATES,
)

if TYPE_CHECKING:
    from backend.repository.repository import DataRepository
    from backend.logic.ml_model import AttentionClassifier
    from backend.logic.rule_engine import RuleEngine

logger = logging.getLogger(__name__)

# ── Module-level constants ─────────────────────────────────────────────────────

ML_WEIGHT_CAP:        float = 0.8   # ML signal never exceeds 80% of the blend
RULE_WEIGHT_FLOOR:    float = 0.2   # Rule signal always contributes at least 20%
COLD_START_THRESHOLD: int   = 50    # Minimum valid sessions before ML is trusted


class FusionEngine:
    """
    Combines AttentionClassifier (ML) and RuleEngine (deterministic) signals.

    Public API
    ----------
    score(feature_vector, title, process) -> FusionResult
        Returns the authoritative state + risk with full audit trail.
    """

    def __init__(
        self,
        repository: "DataRepository",
        classifier: "AttentionClassifier | None" = None,
        rule_engine: "RuleEngine | None" = None,
    ) -> None:
        self._repo       = repository
        self._classifier = classifier
        self._rule_engine = rule_engine

    # ── Legacy shim (kept for backward compatibility with main.py) ─────────────

    def fuse_scores(
        self,
        ml_predicted_state: str,
        ml_risk_score: float,
        rule_state: str,
        rule_risk_score: float,
        rule_override_triggered: bool,
    ) -> tuple[str, float]:
        """
        Backward-compatible API for existing main.py call sites.

        Args:
            ml_predicted_state:    State string from the classifier.
            ml_risk_score:         Risk score from the classifier.
            rule_state:            State string from the rule engine.
            rule_risk_score:       Risk score from the rule engine.
            rule_override_triggered: True if a hard rule fired (confidence==1.0).

        Returns:
            (final_state, final_risk)
        """
        try:
            N = self._repo.count_valid_sessions()
        except Exception:
            N = 0

        w_ml, w_rule = self._compute_weights(N)

        if rule_override_triggered:
            # Hard rule → state is authoritative; risk is blended
            final_state = rule_state
            final_risk  = (rule_risk_score * w_rule) + (ml_risk_score * w_ml)
        else:
            # No hard rule → ML picks state; risk is ML-driven at cold start
            final_state = ml_predicted_state
            final_risk  = (ml_risk_score * w_ml) + (rule_risk_score * w_rule)

        final_risk = max(0.0, min(1.0, final_risk))

        # Validate — fall back to Unknown rather than letting bad strings propagate
        if final_state not in VALID_STATES:
            final_state = "Unknown"

        return final_state, final_risk

    # ── Primary API ────────────────────────────────────────────────────────────

    def score(
        self,
        feature_vector: FeatureVector,
        window_title: str,
        process_name: str,
    ) -> FusionResult:
        """
        Compute a fully-attributed FusionResult for the current session window.

        Constraint:
            If rule_result.confidence == 1.0, final_state MUST equal
            rule_result.assigned_state. ML only influences final_risk.

        Args:
            feature_vector: Current FeatureVector from the feature engineer.
            window_title:   Active window title (passed to rule engine).
            process_name:   Active process name (passed to rule engine).

        Returns:
            FusionResult with all weight and signal fields populated.
        """
        # ── 1. Determine weights based on training data volume ────────────────
        try:
            N = self._repo.count_valid_sessions()
        except Exception as exc:
            logger.warning("count_valid_sessions failed: %s — treating as cold-start.", exc)
            N = 0

        w_ml, w_rule = self._compute_weights(N)

        # ── 2. Rule engine evaluation ─────────────────────────────────────────
        rule_result = None
        if self._rule_engine is not None:
            try:
                rule_result = self._rule_engine.evaluate(
                    feature_vector=feature_vector,
                    window_title=window_title,
                    process_name=process_name,
                )
            except Exception as exc:
                logger.warning("RuleEngine.evaluate() failed: %s", exc)

        # Synthesize a passthrough if rule engine is unavailable
        if rule_result is None:
            from backend.repository.models import RuleResult
            rule_result = RuleResult(
                fired_protocol=None,
                assigned_state="Unknown",
                risk_score_override=0.0,
                confidence=0.0,
                reason="No rule engine available.",
            )

        # ── 3. ML classifier prediction ────────────────────────────────────────
        ml_state:      str   = "Unknown"
        ml_risk:       float = 0.5
        ml_confidence: float = 0.0

        if self._classifier is not None and w_ml > 0.0:
            try:
                x = np.array([
                    feature_vector.interaction_density,
                    feature_vector.scroll_velocity,
                    feature_vector.context_entropy,
                    feature_vector.core_tool_ratio,
                    feature_vector.time_of_day,
                ], dtype=np.float32)
                ml_state, ml_risk = self._classifier.predict(x)

                # Extract max-probability as ml_confidence
                probs = self._classifier._model.predict_proba(x.reshape(1, -1))[0]  # type: ignore
                ml_confidence = float(np.max(probs))
            except ModelNotTrainedError:
                logger.info("Classifier not yet trained — cold-start blend applied.")
                w_ml, w_rule = 0.0, 1.0
            except Exception as exc:
                logger.warning("Classifier prediction failed: %s", exc)

        # ── 4. Fusion constraint ──────────────────────────────────────────────
        hard_rule = rule_result.confidence == 1.0

        if hard_rule:
            # Hard rule wins state unconditionally — only risk is blended
            final_state = rule_result.assigned_state
            final_risk  = (rule_result.risk_score_override * w_rule) + (ml_risk * w_ml)
        else:
            # Soft or no rule — ML drives state, risk blended normally
            final_state = ml_state if w_ml > 0.0 else rule_result.assigned_state
            final_risk  = (ml_risk * w_ml) + (rule_result.risk_score_override * w_rule)

        final_risk  = float(max(0.0, min(1.0, final_risk)))
        if final_state not in VALID_STATES:
            final_state = "Unknown"

        return FusionResult(
            final_state=final_state,
            final_risk=final_risk,
            ml_weight=w_ml,
            rule_weight=w_rule,
            rule_result=rule_result,
            ml_confidence=ml_confidence,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _compute_weights(N: int) -> tuple[float, float]:
        """
        Compute (w_ml, w_rule) from the valid session count N.

        Formula:
            w_ml   = min(ML_WEIGHT_CAP, N / 500)  if N >= COLD_START_THRESHOLD else 0.0
            w_rule = max(RULE_WEIGHT_FLOOR, 1.0 - w_ml)
        """
        if N < COLD_START_THRESHOLD:
            return 0.0, 1.0
        w_ml   = min(ML_WEIGHT_CAP, N / 500.0)
        w_rule = max(RULE_WEIGHT_FLOOR, 1.0 - w_ml)
        return w_ml, w_rule
