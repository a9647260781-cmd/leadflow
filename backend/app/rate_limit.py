import threading
import time
from collections import defaultdict, deque


class FixedWindowRateLimiter:
    """Small in-process limiter suitable for a single API process MVP."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return max(1, int(window_seconds - (now - events[0]) + 0.999))
            events.append(now)
        return None

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


rate_limiter = FixedWindowRateLimiter()
