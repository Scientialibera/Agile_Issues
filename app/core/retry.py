from __future__ import annotations

import logging
import time
from typing import Callable, Iterable

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)

logger = logging.getLogger("agile_issues.retry")


def retry_external_call(
    func: Callable[..., object],
    *,
    max_retries: int = 3,
    backoff_seconds: float = 2.0,
    retry_exceptions: Iterable[type[BaseException]] | None = None,
) -> Callable[..., object]:
    """Wrap *func* so transient failures are retried with exponential backoff.

    Auth errors are never retried.
    """
    exceptions = tuple(retry_exceptions) if retry_exceptions else _default_retry_exceptions()

    def wrapper(*args, **kwargs):
        attempt = 0
        while True:
            try:
                return func(*args, **kwargs)
            except exceptions as exc:
                attempt += 1
                if _is_auth_error(exc) or attempt > max_retries:
                    raise
                sleep_for = backoff_seconds * (2 ** (attempt - 1))
                logger.info(
                    "Retrying after %s (attempt %s, wait %.1fs)",
                    type(exc).__name__,
                    attempt,
                    sleep_for,
                )
                time.sleep(sleep_for)

    return wrapper


def _default_retry_exceptions() -> tuple[type[BaseException], ...]:
    return (
        APIConnectionError,
        APITimeoutError,
        APIError,
        RateLimitError,
    )


def _is_auth_error(exc: BaseException) -> bool:
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return True
    return False
