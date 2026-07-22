"""SQLAlchemy engine + session factory for the Supabase canonical store."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _make_engine():
    if not settings.sqlalchemy_url:
        # Engine is created lazily; tests that don't touch the DB never call this.
        raise RuntimeError("DATABASE_URL is not set — cannot connect to the canonical store.")
    return create_engine(
        settings.sqlalchemy_url,
        pool_size=settings.database_pool_size,
        max_overflow=0,  # No burst connections: Supabase pooler has a hard cap.
        pool_pre_ping=True,
        future=True,
        connect_args={
            # SPEC §8: keep critical-path queries fast; statement timeout is a guardrail.
            "options": f"-c statement_timeout={settings.database_statement_timeout_ms}"
        },
    )


_engine = None
SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, SessionLocal
    if _engine is None:
        _engine = _make_engine()
        SessionLocal = sessionmaker(bind=_engine, autoflush=False, future=True)
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session bound to the canonical store."""
    get_engine()
    assert SessionLocal is not None
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
