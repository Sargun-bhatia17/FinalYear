"""
behavior_engine.py
------------------
Pure mathematical scoring calculators for behavior analysis.
All functions are pure, deterministic, and free of side effects.
"""

import math
import logging
from datetime import datetime
from backend.repository.models import RawEvent, DataQuality

logger = logging.getLogger(__name__)

# Module-level constants
DECAY_LAMBDA = 0.05
SCROLL_NORMALIZATION_CAP = 800.0
ID_NORMALIZATION_CAP = 300.0

DISTANCE_MATRIX = {
    ("Core_Tool", "Core_Tool"): 0.0,
    ("Core_Tool", "Supporting_Tool"): 0.1,
    ("Core_Tool", "Leisure"): 1.0,
    
    ("Supporting_Tool", "Core_Tool"): 0.0,
    ("Supporting_Tool", "Supporting_Tool"): 0.0,
    ("Supporting_Tool", "Leisure"): 0.8,
    
    ("Leisure", "Core_Tool"): 0.2,
    ("Leisure", "Supporting_Tool"): 0.2,
    ("Leisure", "Leisure"): 0.0
}


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse a datetime string from sqlite into a datetime object. (Internal helper)"""
    # Standard SQLite datetime formats: YYYY-MM-DD HH:MM:SS or ISO format
    ts_clean = ts_str.replace(" ", "T")
    try:
        return datetime.fromisoformat(ts_clean)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(ts_clean, fmt)
            except ValueError:
                continue
        raise ValueError(f"Could not parse event timestamp: {ts_str}")


def calculate_interaction_density(events: list[RawEvent]) -> float:
    """Calculate time-decayed interaction density normalized to 0.0 - 1.0."""
    if not events:
        # Return 0.0 because there are no interactions to density count.
        return 0.0

    # Parse timestamps to find the reference "now" time (latest event time)
    try:
        event_times = [_parse_timestamp(ev["timestamp"]) for ev in events]
    except (KeyError, ValueError) as exc:
        logger.error("Failed to parse event timestamps in calculate_interaction_density: %s", exc)
        # Handle malformed timestamps by using a fallback time increment
        event_times = [datetime.fromtimestamp(i * 5) for i in range(len(events))]

    now = max(event_times)
    total_weighted_interactions = 0.0

    for ev, ev_time in zip(events, event_times):
        t = (now - ev_time).total_seconds()
        weight = math.exp(-DECAY_LAMBDA * t)
        interactions = ev.get("keystroke_count", 0) + ev.get("mouse_click_count", 0)
        total_weighted_interactions += weight * interactions

    normalized = total_weighted_interactions / ID_NORMALIZATION_CAP
    return max(0.0, min(1.0, normalized))


def calculate_scroll_velocity(events: list[RawEvent]) -> float:
    """Calculate scroll velocity in active scroll sub-windows normalized to 0.0 - 1.0."""
    if not events:
        # Return 0.0 because no events are available to extract scroll data from.
        return 0.0

    # Identify active scroll sub-windows (contiguous groups of events where scroll_delta_y != 0)
    groups = []
    current_group = []

    for ev in events:
        if ev.get("scroll_delta_y", 0) != 0:
            current_group.append(ev)
        else:
            if current_group:
                groups.append(current_group)
                current_group = []
    if current_group:
        groups.append(current_group)

    if not groups:
        # Return 0.0 because there were no contiguous scrolling intervals detected.
        return 0.0

    total_scroll = sum(abs(ev.get("scroll_delta_y", 0)) for group in groups for ev in group)
    total_duration = 0.0

    for group in groups:
        if len(group) == 1:
            total_duration += 5.0
        else:
            try:
                ts_first = _parse_timestamp(group[0]["timestamp"])
                ts_last = _parse_timestamp(group[-1]["timestamp"])
                diff = (ts_last - ts_first).total_seconds()
                if diff <= 0.0:
                    # Fallback to nominal single event window if timestamps are identical
                    total_duration += 5.0
                else:
                    total_duration += diff
            except (KeyError, ValueError):
                # Fallback to nominal 5-second polling interval per event inside the group
                total_duration += len(group) * 5.0

    if total_duration <= 0.0:
        # Prevent division by zero if total duration is calculated as 0
        return 0.0

    velocity = total_scroll / total_duration
    normalized = velocity / SCROLL_NORMALIZATION_CAP
    return max(0.0, min(1.0, normalized))


def calculate_context_entropy(events: list[RawEvent], taxonomy: dict[str, str]) -> float:
    """Calculate Shannon entropy for context switching normalized to 0.0 - 1.0."""
    if not events:
        # Return 0.0 because a lack of events represents zero switching uncertainty.
        return 0.0

    category_counts = {}
    for ev in events:
        process_name = ev.get("process_name")
        proc_key = process_name.lower() if process_name else ""
        category = taxonomy.get(proc_key) if proc_key else None
        
        if not category:
            category = "Supporting_Tool"
            logger.warning("Process name '%s' not found in taxonomy, assigning 'Supporting_Tool'", process_name)
            
        category_counts[category] = category_counts.get(category, 0) + 1

    total_events = len(events)
    entropy = 0.0
    for count in category_counts.values():
        p_i = count / total_events
        if p_i > 0.0:
            entropy -= p_i * math.log2(p_i)

    # Normalize by dividing by log2(N) where N = 5 (the five possible categories)
    # This maps 0.0 (one app only) to 1.0 (perfectly uniform chaos).
    normalized_entropy = entropy / math.log2(5.0)
    return max(0.0, min(1.0, normalized_entropy))


def calculate_category_distance(events: list[RawEvent], taxonomy: dict[str, str]) -> float:
    """Calculate the time-decayed average category switching distance normalized to 0.0 - 1.0."""
    if not events:
        # Return 0.0 because an empty event stream has no transitions to measure.
        # This matches the transition count requirement check.
        return 0.0

    try:
        event_times = [_parse_timestamp(ev["timestamp"]) for ev in events]
    except (KeyError, ValueError) as exc:
        logger.error("Failed to parse event timestamps in calculate_category_distance: %s", exc)
        event_times = [datetime.fromtimestamp(i * 5) for i in range(len(events))]

    transitions = []
    prev_category = None

    for i, ev in enumerate(events):
        process_name = ev.get("process_name")
        proc_key = process_name.lower() if process_name else ""
        category = taxonomy.get(proc_key) if proc_key else None
        if not category:
            category = "Supporting_Tool"

        if prev_category is not None and category != prev_category:
            # Category transition occurred at this event's timestamp
            transitions.append({
                "from_cat": prev_category,
                "to_cat": category,
                "timestamp": event_times[i]
            })
        prev_category = category

    if len(transitions) < 2:
        # Explicitly return 0.0 because fewer than 2 transitions do not establish a stable trajectory of switching behavior.
        return 0.0

    now = max(event_times)
    total_weighted_distance = 0.0
    total_weight = 0.0

    for trans in transitions:
        dist = DISTANCE_MATRIX.get((trans["from_cat"], trans["to_cat"]), 0.5)
        t = (now - trans["timestamp"]).total_seconds()
        weight = math.exp(-DECAY_LAMBDA * t)
        total_weighted_distance += dist * weight
        total_weight += weight

    if total_weight <= 0.0:
        # Prevent division by zero if decay weight calculations yield a sum of zero.
        return 0.0

    return max(0.0, min(1.0, total_weighted_distance / total_weight))


def assess_data_quality(event_count: int, window_seconds: int) -> DataQuality:
    """Assess the completeness/quality of the behavioral data."""
    # event_count >= 60 (60 five-second rows = 5 minutes) -> FULL.
    # >= 24 -> PARTIAL.
    # Below 24 -> INSUFFICIENT.
    if event_count >= 60:
        return DataQuality.FULL
    elif event_count >= 24:
        return DataQuality.PARTIAL
    else:
        return DataQuality.INSUFFICIENT
