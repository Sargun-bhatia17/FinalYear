"""
utils/errors.py
---------------
Custom exceptions and the @retry_on_failure decorator for AttentionLens.

Usage::

    from backend.utils.errors import EngineOfflineError, retry_on_failure

    @retry_on_failure(retries=3, base_delay=0.5)
    def my_db_write(...):
        ...
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Callable, TypeVar, ParamSpec

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


# ── Custom exceptions ──────────────────────────────────────────────────────────

class EngineOfflineError(RuntimeError):
    """
    Raised when the AttentionLens analysis engine is not running and a caller
    attempts to request live data (e.g. before the first session completes).
    """


class ModelNotTrainedError(Exception):
    """
    Raised by AttentionClassifier.predict() when called before any model
    has been loaded or trained. Imported here as the canonical location;
    ml_model.py imports from this module.
    """


class DatabaseLockedError(IOError):
    """
    Raised when SQLite returns 'database is locked' (SQLITE_BUSY).
    Indicates a write contention issue — safe to retry with backoff.
    """


# ── Retry decorator ────────────────────────────────────────────────────────────

def retry_on_failure(
    retries: int = 3,
    base_delay: float = 0.5,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator that retries a function up to *retries* times on failure,
    using exponential backoff: delay = base_delay * 2^attempt.

    Args:
        retries:    Maximum number of retry attempts (default 3).
        base_delay: Initial delay in seconds before first retry (default 0.5s).
        exceptions: Exception types that trigger a retry. Defaults to all.

    Example::

        @retry_on_failure(retries=3, base_delay=0.5, exceptions=(sqlite3.OperationalError,))
        def insert_raw_event(self, ...):
            ...
    """
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exc: Exception | None = None
            for attempt in range(retries + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == retries:
                        logger.error(
                            "%s failed after %d retries: %s",
                            fn.__qualname__, retries, exc,
                        )
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "%s attempt %d/%d failed (%s) — retrying in %.2fs",
                        fn.__qualname__, attempt + 1, retries, exc, delay,
                    )
                    time.sleep(delay)
            raise RuntimeError("retry_on_failure: unreachable")   # pragma: no cover
        return wrapper
    return decorator
