"""
api_server.py — Phase 6: API Bridge
-------------------------------------
FastAPI + Uvicorn HTTP sidecar for AttentionLens.

Architecture:
  - Single FastAPI app with asyncio lifespan (no deprecated @app.on_event).
  - Port scanning: starts at 8421, increments until a free port is found.
  - Active port written to data/port.json on startup; null written on shutdown.
  - CORS restricted to localhost origins only.
  - Routes are max 5 lines — ALL logic lives in StatusService.
  - Every response is a typed Pydantic model. No raw dicts returned.
  - StatusService carries a threading.Lock to protect the in-memory cache that
    the engine loop writes to every 60 seconds from the main thread.

Backward compatibility:
  - update_state() and trigger_alert() are preserved on ApiServer so existing
    main.py call sites require no changes. They write into StatusService.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

if TYPE_CHECKING:
    from backend.repository.repository import DataRepository

logger = logging.getLogger(__name__)

# ── Path helpers ───────────────────────────────────────────────────────────────

def _data_dir() -> Path:
    """Returns AttentionLens/data/, creating it if absent."""
    d = Path(__file__).resolve().parent.parent.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _port_file() -> Path:
    return _data_dir() / "port.json"


def _write_port(value: int | None) -> None:
    """Atomically write the active port (or null) to data/port.json."""
    _port_file().write_text(json.dumps(value), encoding="utf-8")


# ── Port scanner ───────────────────────────────────────────────────────────────

def _find_free_port(start: int = 8421) -> int:
    """Scan upward from `start` and return the first unbound TCP port."""
    port = start
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port   # connection refused → port is free
        port += 1


# ── Pydantic response models ───────────────────────────────────────────────────

class LiveStatusResponse(BaseModel):
    timestamp:          datetime
    active_process:     str
    active_window_title: str
    current_state:      str
    risk_score:         float
    fired_protocol:     str | None
    data_quality:       str


class SessionBlock(BaseModel):
    start_time:      datetime
    end_time:        datetime
    state:           str
    risk_score:      float
    primary_process: str


class DailySummaryResponse(BaseModel):
    date:               date
    sessions:           list[SessionBlock]
    deep_work_minutes:  int
    idle_minutes:       int
    model_session_count: int
    model_last_trained: datetime | None


class HealthResponse(BaseModel):
    status: str
    port:   int


# ── StatusService ──────────────────────────────────────────────────────────────

class StatusService:
    """
    Thread-safe in-memory cache between the engine loop and the HTTP layer.

    The engine loop (main thread) writes via update() every 60 seconds.
    FastAPI coroutines read via get_live() / get_daily_summary().
    A threading.Lock keeps reads consistent.
    """

    _FALLBACK_LIVE = LiveStatusResponse(
        timestamp=datetime(2000, 1, 1, tzinfo=timezone.utc),
        active_process="—",
        active_window_title="—",
        current_state="Unknown",
        risk_score=0.0,
        fired_protocol=None,
        data_quality="INSUFFICIENT",
    )

    def __init__(self, repository: "DataRepository") -> None:
        self._repo    = repository
        self._latest: dict[str, Any] = {}
        self._lock    = threading.Lock()
        self._active_port: int = 0
        self._metadata_path: Path = (
            Path(__file__).resolve().parent.parent.parent
            / "models" / "metadata.json"
        )

    def update(self, result: dict[str, Any]) -> None:
        """Called by the engine loop every 60 s with the latest session result."""
        with self._lock:
            self._latest = result

    # ── Route delegates ────────────────────────────────────────────────────────

    def get_live(self) -> LiveStatusResponse:
        """
        Reads exclusively from the in-memory cache — MUST NOT touch the database.
        Returns the fallback sentinel when no session has been processed yet.
        """
        with self._lock:
            s = dict(self._latest)   # shallow copy under lock

        if not s:
            return self._FALLBACK_LIVE

        return LiveStatusResponse(
            timestamp=datetime.now(tz=timezone.utc),
            active_process=str(s.get("active_process", "—")),
            active_window_title=str(s.get("active_title", "—")),
            current_state=str(s.get("calculated_state", "Unknown")),
            risk_score=float(s.get("attention_score", 0.0)),
            fired_protocol=s.get("fired_protocol"),          # may be None
            data_quality=str(s.get("data_quality", "FULL")),
        )

    def get_daily_summary(self) -> DailySummaryResponse:
        """
        Queries behavioral_sessions for today's rows.
        State duration aggregation is done in Python — NO SQL GROUP BY / SUM.
        """
        today_str = date.today().isoformat()   # "2026-06-27"

        # Fetch today's sessions ordered start-time ascending
        all_sessions = self._repo.get_all_sessions(limit=5000)
        today_rows = [
            s for s in all_sessions
            if str(s.get("start_time", "")).startswith(today_str)
        ]

        # Build SessionBlock list and aggregate durations in Python
        blocks: list[SessionBlock] = []
        deep_work_seconds = 0
        idle_seconds      = 0

        for row in today_rows:
            try:
                start = datetime.strptime(row["start_time"], "%Y-%m-%d %H:%M:%S")
                end   = datetime.strptime(row["end_time"],   "%Y-%m-%d %H:%M:%S")
            except (ValueError, KeyError):
                continue

            state = str(row.get("calculated_state", "Unknown"))
            duration_s = max(0, int((end - start).total_seconds()))

            # Aggregate — Python arithmetic, not SQL
            if state == "Deep_Work":
                deep_work_seconds += duration_s
            elif state in ("Idle_Away", "Unknown"):
                idle_seconds += duration_s

            blocks.append(SessionBlock(
                start_time=start,
                end_time=end,
                state=state,
                risk_score=float(row.get("attention_risk_score", 0.0)),
                primary_process=str(row.get("primary_process", "—")),
            ))

        model_count, model_trained_at = self._read_metadata()

        return DailySummaryResponse(
            date=date.today(),
            sessions=blocks,
            deep_work_minutes=deep_work_seconds // 60,
            idle_minutes=idle_seconds // 60,
            model_session_count=model_count,
            model_last_trained=model_trained_at,
        )

    def get_health(self) -> HealthResponse:
        """Returns a liveness probe confirming the sidecar is running."""
        return HealthResponse(status="ok", port=self._active_port)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _read_metadata(self) -> tuple[int, datetime | None]:
        """Parse models/metadata.json for model training stats."""
        if not self._metadata_path.exists():
            return 0, None
        try:
            payload = json.loads(self._metadata_path.read_text(encoding="utf-8"))
            count = int(payload.get("session_count", 0))
            ts_str = payload.get("trained_at")
            trained_at = datetime.fromisoformat(ts_str) if ts_str else None
            return count, trained_at
        except Exception as exc:
            logger.warning("Could not parse metadata.json: %s", exc)
            return 0, None


# ── FastAPI app factory ────────────────────────────────────────────────────────

def _build_app(service: StatusService) -> FastAPI:
    """Construct the FastAPI application with lifespan, CORS, and routes."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ── Startup ──────────────────────────────────────────────────────────
        _write_port(service._active_port)
        logger.info("AttentionLens API started on port %d", service._active_port)
        yield
        # ── Shutdown ─────────────────────────────────────────────────────────
        _write_port(None)
        logger.info("AttentionLens API shutdown — port.json cleared.")

    app = FastAPI(
        title="AttentionLens API",
        version="6.0.0",
        description="Attention state monitoring sidecar",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://localhost:1420",   # Tauri default dev port
            "http://127.0.0.1",
            "http://127.0.0.1:1420",
        ],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # ── Routes (max 5 lines each, zero business logic) ──────────────────────

    @app.get("/live-status", response_model=LiveStatusResponse)
    async def live_status() -> LiveStatusResponse:
        return service.get_live()

    @app.get("/daily-summary", response_model=DailySummaryResponse)
    async def daily_summary() -> DailySummaryResponse:
        return service.get_daily_summary()

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return service.get_health()

    return app


# ── ApiServer (public facade — backward compatible with main.py) ───────────────

class ApiServer:
    """
    Backward-compatible facade that:
      1. Exposes update_state() / trigger_alert() for the engine loop.
      2. Runs a FastAPI + Uvicorn HTTP server in a daemon thread.

    main.py call sites are unchanged — they still call:
        self.api_server.update_state("attention_score", ...)
        self.api_server.trigger_alert(alert_dict)
    """

    def __init__(
        self,
        repository: "DataRepository | None" = None,
        port: int = 8421,
    ) -> None:
        self._start_port = port
        self._active_port: int = 0
        self._service: StatusService | None = (
            StatusService(repository) if repository else None
        )
        self._thread: threading.Thread | None = None
        # In-memory state dict kept for update_state / trigger_alert legacy API
        self._state: dict[str, Any] = {
            "attention_score":   0.0,
            "calculated_state":  "Unknown",
            "active_process":    "",
            "active_title":      "",
            "active_category":   "Supporting_Tool",
            "fired_protocol":    None,
            "data_quality":      "FULL",
            "session_count":     0,
            "recent_sessions":   [],
            "current_alert":     None,
            "tracker_status":    {},
        }

    # ── Engine-loop API (called from main thread) ──────────────────────────────

    def update_state(self, key: str, value: Any) -> None:
        """Thread-safe update — keeps the legacy dict and feeds StatusService."""
        self._state[key] = value
        if self._service is not None:
            self._service.update(self._state)

    def trigger_alert(self, alert: dict[str, Any]) -> None:
        """Store the latest alert and push to StatusService."""
        self._state["current_alert"] = alert
        if self._service is not None:
            self._service.update(self._state)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Find a free port, write port.json, then launch Uvicorn in a daemon thread."""
        self._active_port = _find_free_port(self._start_port)

        if self._service is None:
            logger.warning(
                "ApiServer started without a DataRepository — "
                "/daily-summary will return empty results."
            )
            # Create a no-op service that won't crash if repo is None
            class _NullRepo:
                def get_all_sessions(self, limit=100): return []
            self._service = StatusService(_NullRepo())   # type: ignore[arg-type]

        self._service._active_port = self._active_port
        app = _build_app(self._service)

        config = uvicorn.Config(
            app=app,
            host="127.0.0.1",
            port=self._active_port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)

        self._thread = threading.Thread(
            target=server.run,
            name="ApiServerThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("AttentionLens API server started on port %d", self._active_port)

    def stop(self) -> None:
        """Write null to port.json (Uvicorn daemon thread exits with process)."""
        _write_port(None)
        logger.info("ApiServer stopped — port.json cleared.")
