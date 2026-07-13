"""Retry-with-backoff for transient HTTP failures (connection resets, 5xx, timeouts)."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import httpx

T = TypeVar("T")
_TRANSIENT = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.PoolTimeout)


def with_retry(fn: Callable[[], T], attempts: int = 4, base: float = 0.6) -> T:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except _TRANSIENT as e:
            last = e
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            last = e
        if i < attempts - 1:
            time.sleep(base * (2**i))
    raise last if last else RuntimeError("retry failed")


def retrying_post(*args: object, **kwargs: object) -> httpx.Response:
    """httpx.post + raise_for_status, retried on transient failures."""
    def _do() -> httpx.Response:
        resp = httpx.post(*args, **kwargs)  # type: ignore[arg-type]
        resp.raise_for_status()
        return resp
    return with_retry(_do)
