"""Unit tests for Phase 3 behavior engine calculations."""

import pytest
import datetime
from backend.repository.models import DataQuality
from backend.logic.behavior_engine import (
    calculate_interaction_density,
    calculate_scroll_velocity,
    calculate_context_entropy,
    calculate_category_distance,
    assess_data_quality,
)


def test_calculate_interaction_density_empty():
    """Test that calculate_interaction_density([]) returns 0.0 without error."""
    assert calculate_interaction_density([]) == 0.0


def test_calculate_interaction_density_decay():
    """Test that heavy early activity decays lower than identical activity that was recent."""
    # Events with activity 60 seconds before reference "now"
    events_early = [
        {
            "id": 1,
            "timestamp": "2026-06-26 12:00:00",
            "process_name": "Code.exe",
            "window_title": "main.py",
            "keystroke_count": 10,
            "mouse_click_count": 5,
            "scroll_delta_y": 0,
        },
        {
            "id": 2,
            "timestamp": "2026-06-26 12:01:00",
            "process_name": "Code.exe",
            "window_title": "main.py",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 0,
        },
    ]

    # Events with same activity at reference "now" (which is 12:01:00)
    events_recent = [
        {
            "id": 1,
            "timestamp": "2026-06-26 12:00:00",
            "process_name": "Code.exe",
            "window_title": "main.py",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 0,
        },
        {
            "id": 2,
            "timestamp": "2026-06-26 12:01:00",
            "process_name": "Code.exe",
            "window_title": "main.py",
            "keystroke_count": 10,
            "mouse_click_count": 5,
            "scroll_delta_y": 0,
        },
    ]

    val_early = calculate_interaction_density(events_early)
    val_recent = calculate_interaction_density(events_recent)

    assert val_early < val_recent
    assert val_early > 0.0
    assert val_recent > 0.0


def test_calculate_scroll_velocity_burst():
    """Test that calculate_scroll_velocity on a 3-second burst returns higher than the same pixels spread across 60 seconds."""
    events_burst = [
        {
            "id": 1,
            "timestamp": "2026-06-26 12:00:00",
            "process_name": "Code.exe",
            "window_title": "main.py",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 100,
        },
        {
            "id": 2,
            "timestamp": "2026-06-26 12:00:03",
            "process_name": "Code.exe",
            "window_title": "main.py",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 200,
        },
    ]

    events_spread = [
        {
            "id": 1,
            "timestamp": "2026-06-26 12:00:00",
            "process_name": "Code.exe",
            "window_title": "main.py",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 100,
        },
        {
            "id": 2,
            "timestamp": "2026-06-26 12:01:00",
            "process_name": "Code.exe",
            "window_title": "main.py",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 200,
        },
    ]

    val_burst = calculate_scroll_velocity(events_burst)
    val_spread = calculate_scroll_velocity(events_spread)

    assert val_burst > val_spread
    assert val_burst > 0.0
    assert val_spread > 0.0


def test_calculate_context_entropy_single_app():
    """Test that calculate_context_entropy on single-app events returns 0.0."""
    taxonomy = {"code.exe": "Core_Tool"}
    events = [
        {
            "id": 1,
            "timestamp": "2026-06-26 12:00:00",
            "process_name": "code.exe",
            "window_title": "main.py",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 0,
        },
        {
            "id": 2,
            "timestamp": "2026-06-26 12:00:05",
            "process_name": "code.exe",
            "window_title": "main.py",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 0,
        },
    ]

    assert calculate_context_entropy(events, taxonomy) == 0.0


def test_assess_data_quality():
    """Test that assess_data_quality returns appropriate levels based on event count."""
    assert assess_data_quality(10, 300) == DataQuality.INSUFFICIENT
    assert assess_data_quality(24, 300) == DataQuality.PARTIAL
    assert assess_data_quality(60, 300) == DataQuality.FULL


def test_calculate_category_distance():
    """Test that calculate_category_distance properly calculates switching distance."""
    taxonomy = {
        "code.exe": "Core_Tool",
        "chrome.exe": "Leisure",
        "slack.exe": "Supporting_Tool"
    }

    events = [
        {
            "id": 1,
            "timestamp": "2026-06-26 12:00:00",
            "process_name": "code.exe",
            "window_title": "main.py",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 0,
        },
        {
            "id": 2,
            "timestamp": "2026-06-26 12:00:05",
            "process_name": "chrome.exe",
            "window_title": "YouTube",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 0,
        },
        {
            "id": 3,
            "timestamp": "2026-06-26 12:00:10",
            "process_name": "slack.exe",
            "window_title": "Workspace",
            "keystroke_count": 0,
            "mouse_click_count": 0,
            "scroll_delta_y": 0,
        },
    ]

    dist = calculate_category_distance(events, taxonomy)
    assert dist > 0.0
