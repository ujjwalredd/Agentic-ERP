from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create the pgvector extension, all tables, and seed demo data if empty."""
    from app.db import models  # noqa: F401  (register mappers)
    from app.db.seed import seed_if_empty

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine)

    # backend and worker both call init_db() at startup. Serialize seeding with a
    # session-level advisory lock so only one process seeds and the other skips.
    db = SessionLocal()
    try:
        db.execute(text("SELECT pg_advisory_lock(872312001)"))
        seed_if_empty(db)
        db.execute(text("SELECT pg_advisory_unlock(872312001)"))
    finally:
        db.close()
