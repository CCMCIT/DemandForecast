"""Engine and session factory. The DB owns the schema; we never create or alter it."""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import DB_CONNECTION_STRING

engine = create_engine(DB_CONNECTION_STRING)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def session_scope():
    """A session that is always closed. For read-only work (e.g. fail-fast
    guards); callers that write still manage their own commit/rollback."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
