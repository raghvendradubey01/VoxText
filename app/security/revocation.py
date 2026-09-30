"""In-memory revocation list for signed-out session tokens.

Session tokens are self-contained JWTs, so clearing the cookie on sign-out does
not stop an already-captured token from being replayed until it expires.  ``/logout``
therefore also records the token's ``jti`` here, and validation refuses it.

Single-process only, exactly like the rate limiter: a multi-worker deployment
must move this to a shared store (Redis) - see the README notes.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionRevoker:
    """Remembers revoked ``jti`` values until the token would have expired anyway."""

    max_entries: int = 20_000
    _expires_at: dict[str, float] = field(default_factory=dict)  # jti -> unix expiry
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def revoke(self, token_id: str, expires_at: datetime) -> None:
        """Invalidate ``token_id`` from now until ``expires_at``."""
        if not token_id:
            # A token without jti cannot be named, so it cannot be revoked.
            # create_session_token always sets one; this guards hand-issued tokens.
            return
        with self._lock:
            self._forget_expired(time.time())
            self._expires_at[token_id] = expires_at.timestamp()

    def is_revoked(self, token_id: str) -> bool:
        if not token_id:
            return False
        now = time.time()
        with self._lock:
            expiry = self._expires_at.get(token_id)
            if expiry is None:
                return False
            if expiry <= now:
                # Past its own expiry: the signature check rejects it anyway.
                self._expires_at.pop(token_id, None)
                return False
            return True

    def _forget_expired(self, now: float) -> None:
        """Keep the map bounded; called while the lock is held."""
        if len(self._expires_at) < self.max_entries:
            return
        for stale in [k for k, v in self._expires_at.items() if v <= now]:
            self._expires_at.pop(stale, None)
        # Nothing had expired yet (a burst of fresh sign-outs): drop the entries
        # that will expire soonest so the map cannot grow without limit.
        overflow = len(self._expires_at) - self.max_entries + 1
        if overflow > 0:
            for stale in sorted(self._expires_at, key=self._expires_at.get)[:overflow]:
                self._expires_at.pop(stale, None)

    def reset_all(self) -> None:
        """Forget every revocation (used by tests and admin tooling)."""
        with self._lock:
            self._expires_at.clear()


session_revoker = SessionRevoker()
