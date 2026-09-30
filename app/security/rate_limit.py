"""In-memory sliding-window rate limiter.

Used to blunt credential-stuffing against the sign-in endpoint.  Intentionally
dependency-free; a multi-worker deployment should replace it with a shared store
(Redis) - see the README notes.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

from ..config import get_settings
from .errors import RateLimitError


@dataclass
class SlidingWindowLimiter:
    """Allow at most ``max_attempts`` events per ``window_seconds`` per key."""

    max_attempts: int
    window_seconds: int
    max_keys: int = 5000
    _events: dict[str, deque[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _pruned(self, key: str, now: float) -> deque[float]:
        bucket = self._events.get(key)
        if bucket is None:
            bucket = deque()
            self._events[key] = bucket
        cutoff = now - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if not bucket:
            del self._events[key]
            return deque()
        return bucket

    def _drop_stale_keys(self, now: float) -> None:
        if len(self._events) <= self.max_keys:
            return
        cutoff = now - self.window_seconds
        for stale in [k for k, v in self._events.items() if not v or v[-1] <= cutoff]:
            self._events.pop(stale, None)

    def check(self, key: str, detail: str | None = None) -> None:
        """Raise :class:`RateLimitError` when the window is exhausted."""
        now = time.monotonic()
        with self._lock:
            bucket = self._pruned(key, now)
            if len(bucket) >= self.max_attempts:
                retry_after = self.window_seconds - (now - bucket[0])
                raise RateLimitError(
                    detail
                    or "Too many attempts. Please try again later.",
                    retry_after_seconds=int(max(1, retry_after)),
                )

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._drop_stale_keys(now)
            self._events.setdefault(key, deque()).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def reset_all(self) -> None:
        """Forget every recorded attempt (used by tests and admin tooling)."""
        with self._lock:
            self._events.clear()

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            return max(0, self.max_attempts - len(self._pruned(key, now)))


_settings = get_settings()
login_limiter = SlidingWindowLimiter(
    max_attempts=_settings.login_max_attempts,
    window_seconds=_settings.login_window_seconds,
)


def client_identity(request, scope: str, identifier: str | None = None) -> str:
    """Build a limiter key from the client address and (optionally) the account.

    ``request.client.host`` is the direct peer.  Behind a reverse proxy, mount
    ``ProxyHeadersMiddleware`` so the real client IP is recognised.
    """
    host = "-"
    if getattr(request, "client", None) is not None:
        host = request.client.host or "-"
    if identifier:
        host = f"{host}:{identifier}"
    return f"{scope}:{host}"
