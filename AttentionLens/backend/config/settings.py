"""
config/settings.py
-------------------
Centralised application settings via pydantic-settings.

All magic numbers previously hardcoded across the codebase live here.
Values can be overridden at runtime by creating a .env file in the
AttentionLens project root (AttentionLens/.env).

Usage::

    from backend.config.settings import settings

    port = settings.api_port
    threshold = settings.cold_start_threshold
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root = AttentionLens/ (two levels above this file: config/ → backend/ → AttentionLens/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """
    Single source of truth for all configurable values.

    Precedence (highest → lowest):
        1. Environment variables
        2. .env file
        3. Field defaults below
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API Server ─────────────────────────────────────────────────────────────
    api_port:          int   = Field(default=8421,     description="Starting port for port scanner")
    api_host:          str   = Field(default="127.0.0.1", description="HTTP bind address")

    # ── Tracker ────────────────────────────────────────────────────────────────
    poll_interval_s:   float = Field(default=1.0,   description="Window polling interval (seconds)")
    flush_interval_s:  float = Field(default=5.0,   description="Raw event flush interval (seconds)")
    session_interval_s: float = Field(default=60.0, description="Behavioural session window (seconds)")
    idle_threshold_s:  float = Field(default=180.0, description="Seconds of zero input before idle")
    max_title_length:  int   = Field(default=512,   description="Max window title chars stored")
    max_retry_queue:   int   = Field(default=12,    description="Max raw events in the retry queue")

    # ── ML & Fusion ────────────────────────────────────────────────────────────
    cold_start_threshold: int   = Field(default=50,  description="Min valid sessions before ML trusted")
    ml_weight_cap:        float = Field(default=0.8, description="Max fraction ML contributes to blend")
    rule_weight_floor:    float = Field(default=0.2, description="Min fraction rules contribute to blend")
    ml_n_sessions_full:   int   = Field(default=500, description="Sessions at which w_ml reaches cap")

    # ── Retraining Daemon ──────────────────────────────────────────────────────
    retrain_min_new_rows:    int = Field(default=100, description="New rows before retraining fires")
    retrain_max_days:        int = Field(default=7,   description="Max days since last retrain")
    retrain_check_interval_s: int = Field(default=60, description="Daemon wake-up interval (seconds)")

    # ── Rule Engine ────────────────────────────────────────────────────────────
    ghost_focus_threshold_s:  int   = Field(default=180, description="Seconds of zero input → P3 fires")
    pondering_soft_alert_min: int   = Field(default=20,  description="Pondering streak alert threshold (min)")
    pending_timeout_min:      int   = Field(default=20,  description="Unknown queue timeout (min)")
    leisure_scroll_risk_floor: float = Field(default=0.75, description="Clamped risk for P2 (comic loophole)")
    min_id_for_deep_work:     int   = Field(default=20,   description="Raw interaction count for P4-A")

    # ── Logging ────────────────────────────────────────────────────────────────
    log_level:         str   = Field(default="INFO",          description="Root logger level")
    log_max_bytes:     int   = Field(default=10 * 1024 * 1024, description="Log file max size (bytes)")
    log_backup_count:  int   = Field(default=5,               description="Rotated log files to keep")

    # ── Database ───────────────────────────────────────────────────────────────
    db_retain_days:    int   = Field(default=30, description="Days of raw events to keep after pruning")

    # ── Paths (derived, not env-overridable at this level) ─────────────────────
    @property
    def data_dir(self) -> Path:
        d = _PROJECT_ROOT / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def models_dir(self) -> Path:
        d = _PROJECT_ROOT / "models"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def log_dir(self) -> Path:
        d = _PROJECT_ROOT / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def port_file(self) -> Path:
        return self.data_dir / "port.json"


# ── Module-level singleton ─────────────────────────────────────────────────────
settings = Settings()
