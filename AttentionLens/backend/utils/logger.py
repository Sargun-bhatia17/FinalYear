"""
utils/logger.py
---------------
Configures the root logger for AttentionLens with:
  - RotatingFileHandler: 10MB limit, 5 backups, written to logs/attentionlens.log
  - StreamHandler (stderr): for console visibility during development
  - Structured format: timestamp | level | module | message

Call configure_logging() once at process startup (in main.py __main__ block).
After that, every module gets a correctly configured logger via:

    logger = logging.getLogger(__name__)

Usage::

    from backend.utils.logger import configure_logging
    configure_logging()
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False   # guard against double-initialisation


def configure_logging(
    log_dir: Path | None = None,
    level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> None:
    """
    Configure the root logger with rotating file + stderr stream handlers.

    Args:
        log_dir:      Directory for log files. Defaults to AttentionLens/logs/.
        level:        Root log level string (default "INFO").
        max_bytes:    Max size of each log file before rotation (default 10MB).
        backup_count: Number of rotated files to keep (default 5).
    """
    global _configured
    if _configured:
        return
    _configured = True

    if log_dir is None:
        # Default: AttentionLens/logs/  (two levels above this file)
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "attentionlens.log"
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # ── Rotating file handler ─────────────────────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(numeric_level)

    # ── Console handler (INFO+ to stderr) ─────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # ── Root logger configuration ─────────────────────────────────────────────
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    root_logger.info(
        "Logging configured — level=%s file=%s (max=%dMB, backups=%d)",
        level, log_file, max_bytes // (1024 * 1024), backup_count,
    )
