"""Bounded retry helper for transient failures.

Provides a single retry mechanism used across the pipeline for operations
that can fail transiently (network, rate limits, 5xx). Non-recoverable
errors (auth, validation, quota) are never retried — retrying those would
just burn quota/requests and delay the inevitable failure.

Usage::

    from src.utils.retry import retry_transient

    def call():
        ...  # may raise

    try:
        retry_transient(
            call,
            attempts=3,
            base_delay=1.0,
            backoff=2.0,
            recoverable=lambda e: isinstance(e, TransientError),
            context="fetch data",
        )
    except TransientError as e:
        ...  # exhausted retries
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_transient(
    func: Callable[[], T],
    *,
    attempts: int,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    recoverable: Callable[[Exception], bool],
    context: str = "operation",
) -> T:
    """Call ``func`` with bounded retries on recoverable failures.

    Args:
        func: The callable to invoke (zero-argument).
        attempts: Total attempts including the first call. Must be >= 1.
        base_delay: Base sleep seconds before the first retry.
        backoff: Multiplier applied to the delay after each failure.
        recoverable: Predicate deciding whether an exception may be retried.
            Auth/validation errors should return False.
        context: Human-readable description used in log messages.

    Returns:
        The result of the first successful call.

    Raises:
        Exception: The last exception once attempts are exhausted, or the
            first non-recoverable exception immediately.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    delay = base_delay
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            if not recoverable(e):
                raise
            if attempt >= attempts:
                logger.warning(
                    f"{context} failed after {attempts} attempts: {e}"
                )
                break
            logger.info(
                f"{context}: transient failure (attempt {attempt}/"
                f"{attempts}); retrying in {delay:.1f}s: {e}"
            )
            time.sleep(delay)
            delay *= backoff

    assert last_error is not None
    raise last_error