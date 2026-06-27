"""
tests/fixtures.py
-----------------
Shared pytest fixtures for AttentionLens backend tests.

Import into any test module with::

    from backend.tests.fixtures import mock_repo, mock_engine, sample_session

Or use conftest.py auto-discovery by placing this file at backend/tests/conftest.py.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.repository.models import (
    DataQuality,
    FeatureVector,
    SessionRecord,
)


# ── Fixture: mock_repo ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_repo(tmp_path: Path):
    """
    In-memory SQLite DataRepository for use in unit tests.

    Creates a fully-initialized repository backed by a temporary file database
    (not :memory:, so the schema can be applied and the context manager works).
    Yields the repository and closes it after the test.
    """
    from backend.repository.repository import DataRepository

    db_path = str(tmp_path / "test_attention.db")
    repo = DataRepository(db_path=db_path)
    yield repo
    repo.close()


# ── Fixture: mock_engine ───────────────────────────────────────────────────────

@pytest.fixture
def mock_engine():
    """
    Dummy feature extractor that returns a static, deterministic FeatureVector.

    Satisfies callers that depend on FeatureEngineer.build_feature_vector()
    without requiring a live database or real event data.

    Returns an object with a single method build_feature_vector() → FeatureVector.
    """
    class _StaticFeatureEngineer:
        def build_feature_vector(self) -> FeatureVector:
            return FeatureVector(
                timestamp=datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc),
                interaction_density=0.35,
                scroll_velocity=0.12,
                context_entropy=0.25,
                category_distance=0.10,
                core_tool_ratio=0.75,
                time_of_day=10.0,
                data_quality=DataQuality.FULL,
                raw_event_count=60,
            )

    return _StaticFeatureEngineer()


# ── Fixture: sample_session ────────────────────────────────────────────────────

@pytest.fixture
def sample_session() -> SessionRecord:
    """
    A valid, fully-populated SessionRecord for use in persistence and
    serialisation tests.

    All field values are realistic and within their expected ranges so
    that tests exercising downstream formatting or aggregation pass
    without additional setup.
    """
    return SessionRecord(
        start_time="2026-06-27 10:00:00",
        end_time="2026-06-27 10:01:00",
        primary_process="code.exe",
        primary_category="Core_Tool",
        scroll_velocity=0.05,
        input_density=0.42,
        has_text_selection=True,
        calculated_state="Deep_Work",
        attention_risk_score=0.08,
    )
