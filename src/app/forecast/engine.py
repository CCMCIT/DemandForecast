"""Single SQLAlchemy engine for the Goldilocks gateways.

Both gateways share ONE engine (pyodbc under SQLAlchemy) so there is a single
connection, config, and transaction story - not two stacks.

Reconciliation note: this mirrors the shape of the data-engineering team's
app/db/session.py on purpose. When the two efforts merge, this collapses into
their engine and this file goes away; nothing above it should need to change.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Collapses into app.config.settings at reconciliation time.
DB_CONNECTION_STRING = os.environ.get("DB_CONNECTION_STRING", "")


def create_db_engine(connection_string: str = DB_CONNECTION_STRING) -> Engine:
    """One engine per process; gateways hold a reference to it."""
    return create_engine(connection_string, pool_pre_ping=True)


engine = create_db_engine()
