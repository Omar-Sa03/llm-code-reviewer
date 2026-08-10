"""
Retry-with-exponential-backoff utility.

Usage:
    from reviewer.retry import retry_with_backoff

    result = retry_with_backoff(
        fn=lambda: call_api(),
        retries=3,
        base_delay=2.0,
        retriable_exceptions=(TimeoutError, RateLimitError),
    )
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""
    def __init__(self, attempts: int, last_error: Exception):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"All {attempts} attempt(s) failed. Last error: {last_error}"
        )


def retry_with_backoff(
    fn: Callable[[], T],
    retries: int = 3,
    base_delay: float = 2.0,
    jitter: float = 0.5,
    retriable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """
    Call ``fn`` up to ``retries`` times, doubling the delay between each attempt
    (exponential backoff with optional jitter).

    Args:
        fn:                    Zero-argument callable to attempt.
        retries:               Maximum number of attempts (including the first one).
        base_delay:            Seconds to wait before the second attempt.
        jitter:                Random ± fraction added to each delay to spread load.
        retriable_exceptions:  Only retry on these exception types.

    Returns:
        The return value of ``fn`` on the first successful attempt.

    Raises:
        RetryExhausted: if every attempt raises a retriable exception.
        Exception:      immediately, if a non-retriable exception is raised.
    """
    import random

    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            return fn()
        except retriable_exceptions as exc:
            last_error = exc
            if attempt == retries:
                break
            delay = base_delay * (2 ** (attempt - 1))
            delay += random.uniform(-jitter, jitter)
            delay = max(0.1, delay)
            logger.warning(
                "Attempt %d/%d failed: %s — retrying in %.1fs",
                attempt, retries, exc, delay,
            )
            time.sleep(delay)

    raise RetryExhausted(attempts=retries, last_error=last_error)
