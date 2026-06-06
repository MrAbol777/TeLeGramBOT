from __future__ import annotations

import logging
import time
from threading import Lock

logger = logging.getLogger(__name__)


class SimpleRateLimiter:
    def __init__(self) -> None:
        self._last_seen: dict[str, float] = {}
        self._lock = Lock()

    def allow(self, key: str, window_seconds: float) -> bool:
        now = time.monotonic()
        with self._lock:
            last = self._last_seen.get(key)
            if last is not None and now - last < window_seconds:
                return False
            self._last_seen[key] = now
            return True


rate_limiter = SimpleRateLimiter()


def parse_int_callback_payload(data: str | None, prefix: str) -> int | None:
    if not data or not data.startswith(prefix):
        return None
    parts = data.split(":", 1)
    if len(parts) != 2:
        return None
    raw_value = parts[1].strip()
    if not raw_value.isdigit():
        return None
    return int(raw_value)

