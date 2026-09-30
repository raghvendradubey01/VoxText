"""Database engine, session factory and declarative base.

SQLite is used for development; the ORM layer keeps the schema portable so the
only change required to move to PostgreSQL is ``DATABASE_URL``.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

IS_SQLITE = settings.database_url.startswith("sqlite")

_engine_kwargs: dict = {"pool_pre_ping": True}
if IS_SQLITE:
    # Sessions are created per request, and FastAPI may run a sync dependency in
    # its threadpool, which would trip SQLite's same-thread check.
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine: Engine = create_engine(settings.database_url, **_engine_kwargs)

if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, connection_record) -> None:
        """Enforce foreign keys and use WAL for concurrent local reads."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        if ":memory:" not in settings.database_url:
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding one session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create any missing tables.

    Intentionally lightweight for development; real deployments should adopt
    Alembic migrations (documented in the README).
    """
    from . import models  # noqa: F401  (ensures models are registered)

    Base.metadata.create_all(bind=engine)


__all__ = [
    "Base",
    "IS_SQLITE",
    "SessionLocal",
    "engine",
    "get_db",
    "init_db",
]
