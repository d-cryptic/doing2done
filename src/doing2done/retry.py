"""Retry-with-backoff for transient HTTP failures (connection resets, 5xx, timeouts)."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import httpx

T = TypeVar("T")
_TRANSIENT = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.PoolTimeout)


def with_retry(fn: Callable[[], T], attempts: int = 6, base: float = 0.8) -> T:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except _TRANSIENT as e:
            last = e
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code != 429 and code < 500:
                raise  # real client error
            last = e
            ra = e.response.headers.get("retry-after")
            if ra and ra.isdigit() and i < attempts - 1:
                time.sleep(min(int(ra), 15))
                continue
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
