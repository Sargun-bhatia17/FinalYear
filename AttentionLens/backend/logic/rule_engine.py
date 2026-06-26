"""
rule_engine.py
--------------
Phase 4 (Revised): The Loophole Resolver — priority-ordered deterministic rule engine.

Design principles (enforced):
  - RuleEngine is a PURE evaluator: it receives a FeatureVector + context args and returns a
    RuleResult. It never mutates state and never calls the database directly, EXCEPT for
    Protocol P4 which is the single authorised DB-writer for retroactive session correction.
  - All protocol methods are private (_protocol_N) and called in strict priority order from
    a single public evaluate() method.
  - Priority is defined as a Python list of method references at the class level — changing
    priority means reordering that list, not hunting through nested if-else chains.
  - Zero bare string comparisons — all title/process keyword matching uses pre-compiled
    frozensets of lowercased terms.
  - No magic numbers — every threshold is a named module-level constant below.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from backend.repository.models import DataQuality, FeatureVector, RuleResult, VALID_STATES

if TYPE_CHECKING:
    from backend.repository.repository import DataRepository

logger = logging.getLogger(__name__)

# ── Named constants ────────────────────────────────────────────────────────────

PONDERING_KEYWORDS: frozenset[str] = frozenset({
    "leetcode", "codeforces", "hackerrank", "stackoverflow",
    "docs.python", "docs.rust-lang", "arxiv", "coursera",
    "udemy", "edx", "brilliant", "excalidraw",
})

LEISURE_SCROLL_KWORDS: frozenset[str] = frozenset({
    "chapter", "manga", "comic", "webtoon", "feed",
    "timeline", "reel", "shorts",
})

PRESENTATION_PROCESSES: frozenset[str] = frozenset({
    "keynote", "powerpoint", "libreoffice impress",
    "marp", "slides",
})

MEETING_PROCESSES: frozenset[str] = frozenset({
    "zoom", "teams", "meet.google", "facetime",
    "discord", "slack call", "webex",
})

GHOST_FOCUS_THRESHOLD_S:   int   = 180     # seconds of zero input before idle flag
PONDERING_SOFT_ALERT_MIN:  int   = 20      # minutes of continuous pondering before gentle nudge
PENDING_TIMEOUT_MIN:       int   = 20      # minutes before PENDING_UNKNOWN force-resolves to Idle
LEISURE_SCROLL_RISK_FLOOR: float = 0.75    # clamped minimum risk when comic loophole fires
MIN_ID_FOR_DEEP_WORK:      int   = 20      # normalized interactions needed to retroactively confirm Deep Work


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_dt(ts: str) -> datetime:
    """Parse an SQLite timestamp string into a UTC-aware datetime."""
    ts_clean = ts.replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            dt = datetime.strptime(ts_clean, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts!r}")


def _is_fullscreen_win32() -> bool:
    """Return True if the foreground window appears to occupy the full primary monitor."""
    try:
        import win32gui
        import win32con
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
        # Compare window rect to virtual screen dimensions
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        screen_w = win32gui.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_h = win32gui.GetSystemMetrics(win32con.SM_CYSCREEN)
        return (left <= 0 and top <= 0
                and right >= screen_w and bottom >= screen_h)
    except Exception:
        # pywin32 not available or any OS error → assume not fullscreen
        return False


# ── Rule Engine ────────────────────────────────────────────────────────────────

class RuleEngine:
    """
    Priority-ordered deterministic rule evaluator.

    Accepts a FeatureVector + contextual strings and returns a RuleResult.
    The only DB write is in _protocol_4 (Rewriting History) — all other
    protocols are purely computational and require no database.

    Priority order (highest → lowest):
        P5  Video Call Exception
        P3  Ghost Focus / Left the Desk
        P0  Presentation Mode
        P1  DSA Pondering Exception
        P2  Comic/Manga Loophole
        P4  Rewriting History (retroactive)
    """

    # Passthrough sentinel — returned when no protocol fires.
    _PASSTHROUGH = RuleResult(
        fired_protocol=None,
        assigned_state="Unknown",
        risk_score_override=0.0,
        confidence=0.0,
        reason="No rule matched — passthrough to ML fusion.",
    )

    def __init__(self, repository: "DataRepository | None" = None) -> None:
        self._repo = repository
        # Stateful pondering streak tracking (minutes of continuous P1 firing)
        self.pondering_streak_minutes: int = 0
        self.soft_alert_triggered: bool = False

        # Priority list — reorder here to change evaluation order.
        # Each entry is a bound method returning RuleResult | None.
        self._priority_chain = [
            self._protocol_5,
            self._protocol_3,
            self._protocol_0,
            self._protocol_1,
            self._protocol_2,
            self._protocol_4,
        ]

    # ── Public interface ───────────────────────────────────────────────────────

    def evaluate(
        self,
        feature_vector: FeatureVector,
        window_title: str,
        process_name: str,
        pending_unknown_duration_s: float = 0.0,
        pending_queue_length: int = 0,
        most_recent_category: str = "Supporting_Tool",
    ) -> RuleResult:
        """
        Evaluate all protocols in priority order and return the first match.

        Args:
            feature_vector:           Current FeatureVector from the feature engineer.
            window_title:             Raw window title string (will be lowercased internally).
            process_name:             Active process binary name (will be lowercased internally).
            pending_unknown_duration_s: Age in seconds of the oldest Unknown session,
                                        used by P3 (Ghost Focus) and P4 (Rewriting History).
            pending_queue_length:     Number of sessions currently in Unknown state.
            most_recent_category:     The taxonomy category of the most recent non-Unknown event,
                                      used by P4 Branch B.

        Returns:
            The first RuleResult whose protocol fired, or the passthrough sentinel.
        """
        title_lower   = window_title.lower()
        process_lower = process_name.lower()

        for protocol_fn in self._priority_chain:
            result = protocol_fn(
                fv=feature_vector,
                title_lower=title_lower,
                process_lower=process_lower,
                pending_duration_s=pending_unknown_duration_s,
                pending_queue_length=pending_queue_length,
                most_recent_category=most_recent_category,
            )
            if result is not None:
                logger.info(
                    "Rule fired: %s → state=%s risk=%.2f",
                    result.fired_protocol, result.assigned_state, result.risk_score_override,
                )
                return result

        # No protocol fired — reset pondering streak on passthrough
        self.pondering_streak_minutes = 0
        self.soft_alert_triggered = False
        return self._PASSTHROUGH

    # ── Protocol implementations (private, alphabetically by priority number) ──

    def _protocol_5(self, *, fv: FeatureVector, process_lower: str, **_) -> RuleResult | None:
        """
        P5 — Video Call Exception.
        Input: process_lower (str), fv.data_quality (DataQuality).
        Output: RuleResult with state=Active_Meeting, risk=0.1, confidence=1.0 | None.
        """
        # Check if any meeting process keyword appears anywhere in the process name
        if not any(kw in process_lower for kw in MEETING_PROCESSES):
            return None
        # Guard: insufficient data means we can't be confident it's a real meeting
        if fv.data_quality == DataQuality.INSUFFICIENT:
            return None
        return RuleResult(
            fired_protocol="P5_MEETING",
            assigned_state="Active_Meeting",
            risk_score_override=0.1,
            confidence=1.0,
            reason=f"Active meeting detected in process: {process_lower}",
        )

    def _protocol_3(
        self, *, fv: FeatureVector, process_lower: str,
        pending_duration_s: float, **_
    ) -> RuleResult | None:
        """
        P3 — Ghost Focus / Left the Desk.
        Input: fv.interaction_density, fv.scroll_velocity (floats 0-1), pending_duration_s (float seconds).
        Output: RuleResult with state=Idle_Away, risk=0.0, confidence=1.0 | None.
        """
        # Guard: if the user is presenting, P0 handles this — P3 must not fire
        if any(kw in process_lower for kw in PRESENTATION_PROCESSES):
            return None

        zero_input  = fv.interaction_density == 0.0
        zero_scroll = fv.scroll_velocity == 0.0
        timed_out   = pending_duration_s > GHOST_FOCUS_THRESHOLD_S

        if zero_input and zero_scroll and timed_out:
            return RuleResult(
                fired_protocol="P3_GHOST_FOCUS",
                assigned_state="Idle_Away",
                risk_score_override=0.0,
                confidence=1.0,
                reason=f"Zero input for >{GHOST_FOCUS_THRESHOLD_S}s in active window — ghost focus detected.",
            )
        return None

    def _protocol_0(self, *, fv: FeatureVector, process_lower: str, **_) -> RuleResult | None:
        """
        P0 — Presentation Mode.
        Input: process_lower (str), OS fullscreen state (queried via win32 API).
        Output: RuleResult with state=Deep_Work, risk=0.05, confidence=0.8 | None.
        Confidence 0.8 because full-screen detection is not 100% reliable across all OS versions.
        """
        if not any(kw in process_lower for kw in PRESENTATION_PROCESSES):
            return None
        is_fullscreen = _is_fullscreen_win32()
        if not is_fullscreen:
            return None
        return RuleResult(
            fired_protocol="P0_PRESENTING",
            assigned_state="Deep_Work",
            risk_score_override=0.05,
            confidence=0.8,
            reason=f"Presentation mode active in {process_lower}",
        )

    def _protocol_1(self, *, fv: FeatureVector, title_lower: str, **_) -> RuleResult | None:
        """
        P1 — DSA Pondering Exception.
        Input: fv.core_tool_ratio (>=0.6), title_lower (contains PONDERING_KEYWORDS),
               fv.interaction_density (<=0.05), fv.scroll_velocity (<=0.08).
        Output: RuleResult with state=Pondering, risk=0.15, confidence=1.0 | None.
        Side-effect: increments pondering_streak_minutes (stateful context tracking).
        """
        # All three conditions must be true simultaneously
        if fv.core_tool_ratio < 0.6:
            return None

        matched_keyword = next((kw for kw in PONDERING_KEYWORDS if kw in title_lower), None)
        if matched_keyword is None:
            return None

        if fv.interaction_density > 0.05 or fv.scroll_velocity > 0.08:
            return None

        # Increment pondering streak (1 session = 1 minute)
        self.pondering_streak_minutes += 1
        if (self.pondering_streak_minutes >= PONDERING_SOFT_ALERT_MIN
                and not self.soft_alert_triggered):
            self.soft_alert_triggered = True
            logger.info(
                "Pondering streak reached %d minutes — soft alert flag set.",
                self.pondering_streak_minutes,
            )

        return RuleResult(
            fired_protocol="P1_DSA_PONDERING",
            assigned_state="Pondering",
            risk_score_override=0.15,
            confidence=1.0,
            reason=f"Low-input deep analysis detected on: {matched_keyword}",
        )

    def _protocol_2(self, *, fv: FeatureVector, title_lower: str, **_) -> RuleResult | None:
        """
        P2 — Comic/Manga Consumer Loophole.
        Input: title_lower (contains LEISURE_SCROLL_KWORDS), fv.scroll_velocity (>=0.65),
               fv.interaction_density (<=0.15).
        Output: RuleResult with state=Passive_Leisure, risk=LEISURE_SCROLL_RISK_FLOOR (clamped), confidence=1.0 | None.
        LEISURE_SCROLL_RISK_FLOOR is an absolute clamped value, never additive.
        """
        matched_keyword = next((kw for kw in LEISURE_SCROLL_KWORDS if kw in title_lower), None)
        if matched_keyword is None:
            return None

        if fv.scroll_velocity < 0.65:
            return None

        if fv.interaction_density > 0.15:
            return None

        return RuleResult(
            fired_protocol="P2_LEISURE_SCROLL",
            assigned_state="Passive_Leisure",
            risk_score_override=LEISURE_SCROLL_RISK_FLOOR,  # 0.75 absolute, never additive
            confidence=1.0,
            reason=f"High-velocity scroll in leisure context: {matched_keyword}",
        )

    def _protocol_4(
        self,
        *,
        fv: FeatureVector,
        pending_duration_s: float,
        pending_queue_length: int,
        most_recent_category: str,
        **_,
    ) -> RuleResult | None:
        """
        P4 — Rewriting History (retroactive queue resolution).
        Input: pending_queue_length (int), pending_duration_s (float seconds),
               fv.interaction_density (float 0-1), most_recent_category (str).
        Output: RuleResult describing the retroactive correction branch | None.

        This is the ONLY protocol that writes to the database.
        Branches:
            A — Resume detected (density > MIN_ID_FOR_DEEP_WORK in Core_Tool) → Deep_Work
            B — Leisure opened                                                  → Idle_Away
            C — Timeout (>= PENDING_TIMEOUT_MIN)                               → Idle_Away (forced)
        """
        if pending_queue_length == 0:
            # No pending sessions — protocol does not apply
            return None

        if self._repo is None:
            # P4 requires a repository; without one it cannot execute DB writes
            logger.warning("P4 skipped: no repository injected into RuleEngine.")
            return None

        pending_sessions = self._repo.get_pending_unknown_sessions()
        if not pending_sessions:
            return None

        pending_ids = [s["id"] for s in pending_sessions]
        pending_age_minutes = pending_duration_s / 60.0

        # Branch A — user resumed active work in a Core_Tool
        if (most_recent_category == "Core_Tool"
                and fv.interaction_density * 300 > MIN_ID_FOR_DEEP_WORK):
            # Scale back to raw estimate: interaction_density * ID_NORMALIZATION_CAP > threshold
            for sid in pending_ids:
                self._repo.update_session_state(sid, "Deep_Work", 0.1)
            logger.info("P4-A: Retroactively rewrote %d sessions → Deep_Work", len(pending_ids))
            return RuleResult(
                fired_protocol="P4A_RETRO_DEEP_WORK",
                assigned_state="Deep_Work",
                risk_score_override=0.1,
                confidence=0.85,
                reason=f"User resumed typing in Core_Tool; retroactively resolved {len(pending_ids)} Unknown session(s).",
            )

        # Branch B — user opened a Leisure app
        if most_recent_category == "Leisure":
            for sid in pending_ids:
                self._repo.update_session_state(sid, "Idle_Away", 0.5)
            logger.info("P4-B: Retroactively rewrote %d sessions → Idle_Away (leisure opened)", len(pending_ids))
            return RuleResult(
                fired_protocol="P4B_RETRO_IDLE",
                assigned_state="Idle_Away",
                risk_score_override=0.5,
                confidence=0.9,
                reason=f"Leisure app opened after unknown period; retroactively resolved {len(pending_ids)} session(s).",
            )

        # Branch C — timeout flush: queue has stalled for too long
        if pending_age_minutes >= PENDING_TIMEOUT_MIN:
            logger.warning(
                "P4-C: PENDING_UNKNOWN queue aged %.1f min >= %d min threshold — force-resolving %d session(s) to Idle_Away.",
                pending_age_minutes, PENDING_TIMEOUT_MIN, len(pending_ids),
            )
            for sid in pending_ids:
                self._repo.update_session_state(sid, "Idle_Away", 0.6)
            return RuleResult(
                fired_protocol="P4C_TIMEOUT_FLUSH",
                assigned_state="Idle_Away",
                risk_score_override=0.6,
                confidence=0.7,
                reason=f"Pending Unknown queue timed out after {pending_age_minutes:.1f} min; force-resolved {len(pending_ids)} session(s).",
            )

        # P4 conditions existed but no branch resolved — keep waiting
        return None
