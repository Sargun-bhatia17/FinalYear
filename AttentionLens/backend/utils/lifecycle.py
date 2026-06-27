"""
utils/lifecycle.py
------------------
ShutdownCoordinator — registers SIGTERM/SIGINT handlers and coordinates a
clean, ordered shutdown of all AttentionLens subsystems.

Shutdown order (preserves data integrity):
  1. Tracker.stop()       — flushes the retry queue, writes final raw event.
  2. RetrainingDaemon.stop() — signals Event; join with timeout.
  3. ApiServer.stop()     — writes null to data/port.json.
  4. DataRepository.close() — closes SQLite connection.

Usage::

    from backend.utils.lifecycle import ShutdownCoordinator

    coordinator = ShutdownCoordinator(
        tracker=tracker,
        retraining_daemon=daemon,
        api_server=api_server,
        repository=repository,
    )
    coordinator.register()   # Hooks SIGTERM + SIGINT
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.tracker.tracker import Tracker
    from backend.logic.retraining_daemon import RetrainingDaemon
    from backend.server.api_server import ApiServer
    from backend.repository.repository import DataRepository

logger = logging.getLogger(__name__)

_DAEMON_JOIN_TIMEOUT_S = 5.0   # seconds to wait for daemon threads on shutdown


class ShutdownCoordinator:
    """
    Manages ordered, graceful shutdown of all AttentionLens subsystems.

    Registers Python signal handlers for SIGTERM and SIGINT (Ctrl-C).
    On first signal: begins shutdown sequence.
    On second signal (impatient user): forces sys.exit(1).
    """

    def __init__(
        self,
        tracker:           "Tracker | None"           = None,
        retraining_daemon: "RetrainingDaemon | None"  = None,
        api_server:        "ApiServer | None"         = None,
        repository:        "DataRepository | None"    = None,
    ) -> None:
        self._tracker           = tracker
        self._retraining_daemon = retraining_daemon
        self._api_server        = api_server
        self._repository        = repository
        self._shutdown_initiated = False
        self._lock = threading.Lock()

    def register(self) -> None:
        """Hook SIGTERM and SIGINT to trigger the shutdown sequence."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT,  self._signal_handler)
        logger.info("ShutdownCoordinator registered (SIGTERM + SIGINT).")

    def shutdown(self, exit_code: int = 0) -> None:
        """
        Execute the shutdown sequence immediately (can also be called directly).
        Thread-safe — multiple concurrent callers collapse to a single execution.
        """
        with self._lock:
            if self._shutdown_initiated:
                return
            self._shutdown_initiated = True

        logger.info("--- AttentionLens shutdown sequence initiated ---")

        # Step 1: Stop tracker — flushes retry queue, writes final raw event.
        self._safe_stop("Tracker", self._tracker)

        # Step 2: Stop retraining daemon — signals threading.Event.
        self._safe_stop("RetrainingDaemon", self._retraining_daemon)

        # Step 3: Stop API server — writes null to data/port.json.
        self._safe_stop("ApiServer", self._api_server)

        # Step 4: Close the database connection.
        if self._repository is not None:
            try:
                self._repository.close()
                logger.info("DataRepository connection closed.")
            except Exception as exc:
                logger.error("DataRepository.close() failed: %s", exc)

        logger.info("--- Shutdown complete — exiting with code %d ---", exit_code)
        sys.exit(exit_code)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle SIGTERM/SIGINT. Second signal forces immediate exit."""
        sig_name = signal.Signals(signum).name
        if self._shutdown_initiated:
            logger.warning("Second %s received — forcing exit.", sig_name)
            sys.exit(1)
        logger.info("Received %s — initiating graceful shutdown.", sig_name)
        # Run shutdown in a new thread so signal handler returns immediately
        threading.Thread(
            target=self.shutdown,
            args=(0,),
            daemon=True,
            name="ShutdownThread",
        ).start()

    def _safe_stop(self, name: str, component: Any) -> None:
        """Call component.stop() if it exists; log errors without crashing."""
        if component is None:
            return
        try:
            component.stop()
            logger.info("%s stopped.", name)
        except Exception as exc:
            logger.error("%s.stop() raised: %s", name, exc)
