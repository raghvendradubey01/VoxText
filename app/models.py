"""ORM models.

Only ``users`` is required for the authentication phase; activity/history tables
are added by later phases against this same declarative base.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp (portable across SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Stored normalised (lower-cased, trimmed) so uniqueness is meaningful.
    email: Mapped[str] = mapped_column(
        String(254), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # bcrypt digest only - plaintext is never stored or returned.
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @staticmethod
    def normalize_email(raw: str) -> str:
        return raw.strip().lower()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id} email={self.email!r}>"
