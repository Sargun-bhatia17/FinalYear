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


# Single source of truth for all valid attention state labels.
# Every function that assigns a state MUST validate against this set.
# Raising immediately on an invalid value prevents silent session record corruption.
VALID_STATES: frozenset[str] = frozenset({
    "Deep_Work",
    "Pondering",
    "Passive_Leisure",
    "Idle_Away",
    "Active_Meeting",
    "Unknown",
})


@dataclass(frozen=True, slots=True)
class RuleResult:
    """
    Strongly-typed output of RuleEngine.evaluate().

    Attributes:
        fired_protocol:      Protocol identifier that fired (e.g. "P1_DSA_PONDERING"),
                             or None if no rule matched (passthrough).
        assigned_state:      Final state string — must be a member of VALID_STATES.
        risk_score_override: Clamped risk score in [0.0, 1.0].
        confidence:          1.0 if a hard rule fired; 0.0 for passthrough.
        reason:              Human-readable description of the trigger for audit logs.
    """

    fired_protocol:      str | None
    assigned_state:      str
    risk_score_override: float
    confidence:          float
    reason:              str

    def __post_init__(self) -> None:
        if self.assigned_state not in VALID_STATES:
            raise ValueError(
                f"RuleResult.assigned_state={self.assigned_state!r} is not in VALID_STATES. "
                f"Allowed values: {sorted(VALID_STATES)}"
            )
        # Clamp risk score defensively — callers should already clamp, but belt-and-suspenders.
        if not (0.0 <= self.risk_score_override <= 1.0):
            object.__setattr__(self, "risk_score_override",
                               max(0.0, min(1.0, self.risk_score_override)))
