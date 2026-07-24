"""Single SQLAlchemy engine for the Goldilocks gateways.

Both gateways share ONE engine (pyodbc under SQLAlchemy) so there is a single
connection, config, and transaction story - not two stacks.

Environment selection now matches the rest of the app: the connection string
comes from app.config.settings.connection_string(env), which reads the
per-environment DB_CONNECTION_STRING_{DEV,UAT,PROD} variables. There is no
separate unsuffixed DB_CONNECTION_STRING any more - that was a second,
undocumented way to point the forecast scripts at a database, and it silently
bypassed the dev/uat/prod split the CLI enforces everywhere else.

Reconciliation note: this deliberately mirrors app/db/session.py's
configure() / lazy-default shape. When the two efforts merge, this collapses
into their engine and this file goes away; nothing above it should need to
change. The forecast layer keeps its own Core engine (not their ORM
sessionmaker) because the gateways drive stored procedures over raw
connections, but both now resolve their connection string the same way.

Usage from a script's CLI, before any DB work:

    from db import engine as engine_module
    engine_module.configure(Env(args.env))
    reads = ReadGateway(engine_module.get_engine())
"""
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config.settings import DEFAULT_ENV, Env, connection_string

_engine: Engine | None = None
_active_env: Env | None = None


def configure(env: Env = DEFAULT_ENV) -> None:
    """Bind the module engine to `env`. Safe to call again to switch.

    pool_pre_ping guards against stale pooled connections, which a long
    training or scoring run can otherwise trip over.
    """
    global _engine, _active_env
    _engine = create_engine(connection_string(env), pool_pre_ping=True)
    _active_env = env


def get_engine() -> Engine:
    """The engine for the active environment, binding the default (dev) on
    first use if configure() was never called.

    Lazy rather than module-level so that importing a forecast module does not
    require a database at import time - tests and ad-hoc imports keep working,
    and a missing .env fails at first use with settings.py's message rather
    than at import with a second, competing one.
    """
    if _engine is None:
        configure()
    return _engine


def active_env() -> Env:
    """The environment currently bound (binding the default if none yet)."""
    if _active_env is None:
        configure()
    return _active_env


def create_db_engine(env: Env = DEFAULT_ENV) -> Engine:
    """A NEW engine for `env`, independent of the module-level one.

    For the rare caller that needs to touch two environments in one process
    (e.g. comparing registered models across dev and uat). Ordinary callers
    want configure() + get_engine().
    """
    return create_engine(connection_string(env), pool_pre_ping=True)
