"""SQLAlchemy engine, session factory and FastAPI database dependency."""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _create_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True, future=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            # WAL + a busy timeout keep reads responsive while the scheduler writes.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


engine = _create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def _apply_sqlite_migrations() -> None:
    """Small forward-only migrations for existing SQLite deployments."""

    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "rooms" in tables:
        columns = {column["name"] for column in inspector.get_columns("rooms")}
        if "description" not in columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE rooms ADD COLUMN description VARCHAR(300)"))
                logger.info("Added rooms.description column")
            except Exception:  # pragma: no cover - depends on the SQLite version
                logger.warning(
                    "Could not add rooms.description; migrate the database manually"
                )

    if "alerts" in tables:
        columns = {column["name"] for column in inspector.get_columns("alerts")}
        if "is_demo" in columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE alerts DROP COLUMN is_demo"))
                logger.info("Dropped legacy alerts.is_demo column")
            except Exception:  # pragma: no cover - depends on the SQLite version
                logger.warning(
                    "Could not drop legacy alerts.is_demo column; recreate the database or migrate manually"
                )


def init_db() -> None:
    """Create tables for all registered models and apply SQLite migrations."""

    from app import models  # noqa: F401  (ensures model modules are imported)

    Base.metadata.create_all(bind=engine)
    _apply_sqlite_migrations()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
