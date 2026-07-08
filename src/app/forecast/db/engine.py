"""Single SQLAlchemy engine for the Goldilocks gateways.

Both gateways share ONE engine (pyodbc under SQLAlchemy) so there is a single
connection, config, and transaction story - not two stacks.

Reconciliation note: this mirrors the shape of the data-engineering team's
app/db/session.py on purpose. When the two efforts merge, this collapses into
their engine and this file goes away; nothing above it should need to change.
Until then it also mirrors app/config/settings.py's .env loading so a forecast
script picks up DB_CONNECTION_STRING without it having to be exported into the
shell/IDE environment first.
"""
import os

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Load .env like app/config/settings.py does. find_dotenv() walks up from the
# CWD to the repo-root .env, so the lookup works regardless of which directory
# the script is launched from (PyCharm, CLI, etc.).
load_dotenv(find_dotenv())

# Collapses into app.config.settings at reconciliation time.
DB_CONNECTION_STRING = os.environ.get("DB_CONNECTION_STRING", "")


def create_db_engine(connection_string: str = DB_CONNECTION_STRING) -> Engine:
    """One engine per process; gateways hold a reference to it.

    Fail with a clear message when the connection string is missing rather than
    handing an empty string to create_engine(), which otherwise surfaces as an
    opaque 'Could not parse SQLAlchemy URL' error.
    """
    if not connection_string:
        raise RuntimeError(
            "DB_CONNECTION_STRING is not set. Add it to your .env at the repo "
            "root (e.g. DB_CONNECTION_STRING=mssql+pyodbc://...) or export it in "
            "the environment before running. This mirrors the loader in "
            "app/config/settings.py."
        )
    return create_engine(connection_string, pool_pre_ping=True)


engine = create_db_engine()
