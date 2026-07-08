"""Engine and session factory. The DB owns the schema; we never create or alter it.

The engine is bound to one of the dev/uat/prod environments via configure(). The
CLI calls configure() once from its --env flag before any DB work. If nothing
configures it, the first SessionLocal() lazily binds the default (dev), so tests
and ad-hoc scripts keep working without ceremony.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import Env, DEFAULT_ENV, connection_string

_engine = None
_session_factory = None
_active_env = None


def configure(env: Env = DEFAULT_ENV) -> None:
    """Bind the engine + session factory to `env`. Safe to call again to switch."""
    global _engine, _session_factory, _active_env
    _engine = create_engine(connection_string(env))
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    _active_env = env


def active_env() -> Env:
    """The environment currently bound (binding the default if none yet)."""
    if _active_env is None:
        configure()
    return _active_env


def SessionLocal():
    """Create a new Session on the active environment's engine.

    Kept callable as SessionLocal() so every existing call site is unchanged; it
    lazily binds the default (dev) engine on first use if configure() wasn't called.
    """
    if _session_factory is None:
        configure()
    return _session_factory()


@contextmanager
def session_scope():
    """A session that is always closed. For read-only work (e.g. fail-fast
    guards); callers that write still manage their own commit/rollback."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()