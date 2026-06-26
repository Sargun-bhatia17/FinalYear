"""
tests/test_rule_engine.py
-------------------------
Unit tests for Phase 4 (Revised): The Loophole Resolver — Rule Engine.

All tests use mock FeatureVectors and mock repositories so the rule engine
can be exercised without a live database connection.
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, call

from backend.repository.models import (
    DataQuality,
    FeatureVector,
    RuleResult,
    VALID_STATES,
)
from backend.logic.rule_engine import (
    RuleEngine,
    LEISURE_SCROLL_RISK_FLOOR,
    PENDING_TIMEOUT_MIN,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_fv(
    interaction_density: float = 0.0,
    scroll_velocity: float = 0.0,
    context_entropy: float = 0.0,
    category_distance: float = 0.0,
    core_tool_ratio: float = 0.8,
    time_of_day: float = 14.0,
    data_quality: DataQuality = DataQuality.FULL,
    raw_event_count: int = 60,
) -> FeatureVector:
    """Helper to create a FeatureVector with sensible defaults for testing."""
    return FeatureVector(
        timestamp=datetime(2026, 6, 26, 14, 0, 0),
        interaction_density=interaction_density,
        scroll_velocity=scroll_velocity,
        context_entropy=context_entropy,
        category_distance=category_distance,
        core_tool_ratio=core_tool_ratio,
        time_of_day=time_of_day,
        data_quality=data_quality,
        raw_event_count=raw_event_count,
    )


def _make_engine(repo=None) -> RuleEngine:
    """Helper to create a RuleEngine with an optional mock repository."""
    return RuleEngine(repository=repo)


# ── Test: P5 fires before P1 ───────────────────────────────────────────────────

class TestProtocolPriority:
    def test_p5_fires_before_p1_when_zoom_and_leetcode(self):
        """P5 (Video Call) must outrank P1 (DSA Pondering).
        If the process is 'zoom' and the title contains 'leetcode',
        P5 should fire and return Active_Meeting — not P1's Pondering."""
        engine = _make_engine()
        fv = _make_fv(
            interaction_density=0.02,   # low enough for P1 to fire
            scroll_velocity=0.01,       # low enough for P1 to fire
            core_tool_ratio=0.9,        # high enough for P1 to fire
            data_quality=DataQuality.FULL,
        )
        result = engine.evaluate(
            feature_vector=fv,
            window_title="LeetCode - Two Sum",
            process_name="zoom",
        )
        assert result.fired_protocol == "P5_MEETING"
        assert result.assigned_state == "Active_Meeting"

    def test_p3_does_not_fire_when_process_is_keynote(self):
        """P3 (Ghost Focus) must NOT fire when process is a presentation app.
        P0 (Presentation Mode) should guard that case — P3 explicitly checks
        for presentation processes and returns None so P0 gets a chance."""
        engine = _make_engine()
        fv = _make_fv(
            interaction_density=0.0,
            scroll_velocity=0.0,
            data_quality=DataQuality.FULL,
        )
        # pending_duration_s > 180 to satisfy P3 trigger conditions
        result = engine.evaluate(
            feature_vector=fv,
            window_title="My Presentation - Keynote",
            process_name="keynote",
            pending_unknown_duration_s=300.0,
        )
        # P3 is guarded; P0 would need fullscreen=True to fire.
        # With no fullscreen mock, neither P3 nor P0 fires → passthrough or P0 fails gracefully.
        assert result.fired_protocol != "P3_GHOST_FOCUS", (
            "P3 must NOT fire when process is a presentation app (keynote)."
        )

    def test_p3_fires_when_no_presentation_process(self):
        """P3 (Ghost Focus) fires for zero-input non-presentation processes."""
        engine = _make_engine()
        fv = _make_fv(interaction_density=0.0, scroll_velocity=0.0)
        result = engine.evaluate(
            feature_vector=fv,
            window_title="Code Editor",
            process_name="code.exe",
            pending_unknown_duration_s=250.0,  # > GHOST_FOCUS_THRESHOLD_S (180)
        )
        assert result.fired_protocol == "P3_GHOST_FOCUS"
        assert result.assigned_state == "Idle_Away"
        assert result.risk_score_override == 0.0


# ── Test: P2 risk score clamp ─────────────────────────────────────────────────

class TestP2Clamping:
    def test_p2_risk_score_is_exactly_leisure_floor(self):
        """P2 must return risk = LEISURE_SCROLL_RISK_FLOOR (0.75) as an absolute
        clamped value, never additive or higher, even if the feature vector
        already implies a higher risk profile."""
        engine = _make_engine()
        fv = _make_fv(
            scroll_velocity=0.9,        # high scroll → triggers P2
            interaction_density=0.05,   # low input → triggers P2
        )
        result = engine.evaluate(
            feature_vector=fv,
            window_title="One Piece Chapter 1123 - MangaReader",
            process_name="chrome.exe",
        )
        assert result.fired_protocol == "P2_LEISURE_SCROLL"
        assert result.risk_score_override == LEISURE_SCROLL_RISK_FLOOR
        assert result.risk_score_override <= 1.0
        assert result.assigned_state == "Passive_Leisure"

    def test_p2_risk_never_exceeds_one(self):
        """Even with extreme scroll values, P2 risk is capped at LEISURE_SCROLL_RISK_FLOOR."""
        engine = _make_engine()
        fv = _make_fv(scroll_velocity=1.0, interaction_density=0.0)
        result = engine.evaluate(
            feature_vector=fv,
            window_title="Webtoon - Chapter 50 Feed",
            process_name="chrome.exe",
        )
        if result.fired_protocol == "P2_LEISURE_SCROLL":
            assert result.risk_score_override <= 1.0
            assert result.risk_score_override == LEISURE_SCROLL_RISK_FLOOR


# ── Test: P1 keyword matching ─────────────────────────────────────────────────

class TestP1Matching:
    def test_p1_does_not_fire_on_non_matching_keyword(self):
        """P1 must NOT fire when title contains 'spreadsheets' (Google Sheets URL).
        'docs.google.com/spreadsheets' does not match any PONDERING_KEYWORDS."""
        engine = _make_engine()
        fv = _make_fv(
            core_tool_ratio=0.9,
            interaction_density=0.02,
            scroll_velocity=0.03,
        )
        result = engine.evaluate(
            feature_vector=fv,
            window_title="docs.google.com/spreadsheets/d/1abc",
            process_name="chrome.exe",
        )
        assert result.fired_protocol != "P1_DSA_PONDERING", (
            "P1 must not fire on 'docs.google.com/spreadsheets' — "
            "only 'docs.python' and 'docs.rust-lang' are in PONDERING_KEYWORDS."
        )

    def test_p1_fires_on_exact_pondering_keyword(self):
        """P1 fires when all three conditions are satisfied with a correct keyword."""
        engine = _make_engine()
        fv = _make_fv(
            core_tool_ratio=0.8,
            interaction_density=0.03,
            scroll_velocity=0.05,
        )
        result = engine.evaluate(
            feature_vector=fv,
            window_title="LeetCode - Problem 42",
            process_name="chrome.exe",
        )
        assert result.fired_protocol == "P1_DSA_PONDERING"
        assert result.assigned_state == "Pondering"
        assert result.risk_score_override == 0.15


# ── Test: P4 Branch C timeout ─────────────────────────────────────────────────

class TestP4BranchC:
    def test_p4_branch_c_fires_after_timeout_and_writes_idle(self):
        """P4 Branch C must fire when pending queue is old enough AND neither Branch A
        nor B has fired. It must call repo.update_session_state for each pending ID."""
        mock_repo = MagicMock()
        # Simulate two pending Unknown sessions
        mock_repo.get_pending_unknown_sessions.return_value = [
            {"id": 101, "start_time": "2026-06-26 13:00:00", "primary_category": "Core_Tool"},
            {"id": 102, "start_time": "2026-06-26 13:01:00", "primary_category": "Core_Tool"},
        ]

        engine = _make_engine(repo=mock_repo)
        fv = _make_fv(
            interaction_density=0.01,   # NOT enough to trigger Branch A (MIN_ID_FOR_DEEP_WORK)
            core_tool_ratio=0.8,
        )
        # Duration: PENDING_TIMEOUT_MIN * 60 + 60 → definitely exceeds timeout
        timeout_s = PENDING_TIMEOUT_MIN * 60 + 60

        result = engine.evaluate(
            feature_vector=fv,
            window_title="code.exe - editing main.py",
            process_name="code.exe",
            pending_unknown_duration_s=timeout_s,
            pending_queue_length=2,
            most_recent_category="Core_Tool",   # Not "Leisure" so Branch B won't fire
        )
        assert result.fired_protocol == "P4C_TIMEOUT_FLUSH"
        assert result.assigned_state == "Idle_Away"
        # Must have called update_session_state for both pending IDs
        mock_repo.update_session_state.assert_any_call(101, "Idle_Away", 0.6)
        mock_repo.update_session_state.assert_any_call(102, "Idle_Away", 0.6)
        assert mock_repo.update_session_state.call_count == 2


# ── Test: passthrough / no match ─────────────────────────────────────────────

class TestPassthrough:
    def test_evaluate_returns_passthrough_when_no_rule_matches(self):
        """evaluate() must return fired_protocol=None and confidence=0.0
        when the FeatureVector and context do not satisfy any protocol."""
        engine = _make_engine()
        fv = _make_fv(
            interaction_density=0.3,    # too high for P1, P2, P3
            scroll_velocity=0.3,        # too high for P1; too low for P2
            core_tool_ratio=0.5,        # below P1 threshold of 0.6
        )
        result = engine.evaluate(
            feature_vector=fv,
            window_title="Generic Document - Word",
            process_name="winword.exe",
            pending_unknown_duration_s=0.0,
            pending_queue_length=0,
        )
        assert result.fired_protocol is None
        assert result.confidence == 0.0


# ── Test: all states in VALID_STATES ─────────────────────────────────────────

class TestValidStates:
    """Parameterised check that every RuleResult produced by the engine
    carries a state that is a member of VALID_STATES."""

    _SCENARIOS = [
        # (description, fv_kwargs, evaluate_kwargs)
        (
            "P5_MEETING",
            dict(data_quality=DataQuality.FULL),
            dict(window_title="Team Standup", process_name="zoom"),
        ),
        (
            "P3_GHOST_FOCUS",
            dict(interaction_density=0.0, scroll_velocity=0.0),
            dict(
                window_title="VS Code",
                process_name="code.exe",
                pending_unknown_duration_s=300.0,
            ),
        ),
        (
            "P1_DSA_PONDERING",
            dict(core_tool_ratio=0.9, interaction_density=0.02, scroll_velocity=0.04),
            dict(window_title="Leetcode - Two Sum", process_name="chrome.exe"),
        ),
        (
            "P2_LEISURE_SCROLL",
            dict(scroll_velocity=0.9, interaction_density=0.05),
            dict(window_title="One Piece Chapter 900 - Manga Feed", process_name="chrome.exe"),
        ),
        (
            "PASSTHROUGH",
            dict(interaction_density=0.4, scroll_velocity=0.2, core_tool_ratio=0.3),
            dict(window_title="Some Window", process_name="unknown.exe"),
        ),
    ]

    @pytest.mark.parametrize("description,fv_kw,ev_kw", _SCENARIOS)
    def test_assigned_state_in_valid_states(self, description, fv_kw, ev_kw):
        """Every RuleResult.assigned_state must be a member of VALID_STATES."""
        engine = _make_engine()
        fv = _make_fv(**fv_kw)
        result = engine.evaluate(feature_vector=fv, **ev_kw)
        assert result.assigned_state in VALID_STATES, (
            f"Scenario '{description}': assigned_state={result.assigned_state!r} "
            f"is not in VALID_STATES={sorted(VALID_STATES)}"
        )
