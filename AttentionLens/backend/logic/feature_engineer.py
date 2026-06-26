"""
feature_engineer.py
-------------------
Orchestrates raw event metrics extraction and builds FeatureVector objects.
Contains no direct math; acts purely as a coordinator delegating to behavior_engine.
"""

import datetime
import logging
from backend.repository.models import FeatureVector, RawEvent
from backend.logic.behavior_engine import (
    calculate_interaction_density,
    calculate_scroll_velocity,
    calculate_context_entropy,
    calculate_category_distance,
    assess_data_quality,
)

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """Coordinator class to extract features and build FeatureVector."""

    def __init__(self, repository):
        """Inject repository dependency from outside."""
        self.repository = repository

    def build_feature_vector(self) -> FeatureVector:
        """Assembles a FeatureVector by calling pure calculator functions."""
        events: list[RawEvent] = self.repository.get_last_n_minutes_events(5)
        taxonomy: dict[str, str] = self.repository.get_taxonomy_snapshot()

        # Call calculators
        density = calculate_interaction_density(events)
        scroll = calculate_scroll_velocity(events)
        entropy = calculate_context_entropy(events, taxonomy)
        distance = calculate_category_distance(events, taxonomy)

        # Compute core tool ratio
        core_tool_count = sum(
            1 for ev in events
            if taxonomy.get((ev.get("process_name") or "").lower()) == "Core_Tool"
        )
        core_ratio = core_tool_count / len(events) if events else 0.0

        # Compute current time of day
        now_dt = datetime.datetime.now()
        time_of_day = now_dt.hour + now_dt.minute / 60.0

        # Assess data quality
        quality = assess_data_quality(len(events), 300)

        # Construct vector
        vector = FeatureVector(
            timestamp=now_dt,
            interaction_density=density,
            scroll_velocity=scroll,
            context_entropy=entropy,
            category_distance=distance,
            core_tool_ratio=core_ratio,
            time_of_day=time_of_day,
            data_quality=quality,
            raw_event_count=len(events),
        )

        logger.debug("Generated FeatureVector: %s", vector)
        return vector
