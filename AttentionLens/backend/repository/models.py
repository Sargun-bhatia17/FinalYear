"""
models.py
---------
Data-shape definitions for AttentionLens.

All structured data passed between layers must use these dataclasses,
never raw tuples or anonymous dicts. This keeps the repository from
becoming a dumping ground for data-shape logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, TypedDict


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """
    Immutable representation of a single 60-second behavioral session.

    This is the primary data-transfer object between the behavior engine
    and the repository layer. Using a frozen dataclass prevents accidental
    mutation after construction.

    Attributes:
        start_time:           Session window start (ISO-8601 string or datetime).
        end_time:             Session window end.
        primary_process:      The dominant process name during this window.
        primary_category:     Taxonomy-resolved category (Core_Tool | Supporting_Tool | Leisure).
        scroll_velocity:      Pixels scrolled per second (S_V).
        input_density:        Total interactions: keystrokes + clicks (I_D).
        has_text_selection:   Whether highlighting/selecting occurred.
        calculated_state:     Final state label (Deep Work | Pondering | Passive Leisure | Idle).
        attention_risk_score: Fusion engine output in range [0.0, 1.0].
    """

    start_time:           str
    end_time:             str
    primary_process:      str
    primary_category:     str
    scroll_velocity:      float
    input_density:        float
    has_text_selection:   bool
    calculated_state:     str
    attention_risk_score: float


@dataclass(frozen=True, slots=True)
class RawEventRecord:
    """
    Typed representation of a single raw_window_events row returned from the DB.

    Attributes:
        id:                Row ID.
        timestamp:         When the event was recorded.
        process_name:      Active process binary name.
        window_title:      Active window title string.
        keystroke_count:   Number of keystrokes in this 5-second interval.
        mouse_click_count: Number of mouse clicks in this 5-second interval.
        scroll_delta_y:    Vertical scroll delta (signed integer).
    """

    id:                int
    timestamp:         str
    process_name:      str
    window_title:      str
    keystroke_count:   int
    mouse_click_count: int
    scroll_delta_y:    int


@dataclass(frozen=True, slots=True)
class TaxonomyEntry:
    """
    Typed representation of a single user_taxonomy row.

    Attributes:
        process_or_keyword: The keyword or process name.
        assigned_category:  Core_Tool | Supporting_Tool | Leisure.
        confidence_weight:  Trust weight for this mapping (0.0 - 1.0).
    """

    process_or_keyword: str
    assigned_category:  str
    confidence_weight:  float = 1.0


class DataQuality(str, Enum):
    FULL         = "FULL"
    PARTIAL      = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class FeatureVector:
    timestamp: datetime
    interaction_density: float      # normalized 0.0–1.0
    scroll_velocity: float          # normalized 0.0–1.0
    context_entropy: float          # normalized 0.0–1.0
    category_distance: float        # already 0.0–1.0
    core_tool_ratio: float          # 0.0–1.0
    time_of_day: float              # 0.0–23.99
    data_quality: DataQuality
    raw_event_count: int


class RawEvent(TypedDict):
    id: int
    timestamp: str
    process_name: str
    window_title: str
    keystroke_count: int
    mouse_click_count: int
    scroll_delta_y: int
