"""Application settings. DB urls and paths come from .env.

Three database environments are configured (dev / uat / prod), each with its own
connection string in .env. The active one is chosen per run (the CLI's --env flag)
and defaults to dev. connection_string(env) returns the matching url;
db.session.configure(env) binds the engine to it.
"""
import os
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class Env(str, Enum):
    DEV = "dev"
    UAT = "uat"
    PROD = "prod"


DEFAULT_ENV = Env.DEV

# Env -> the .env variable holding that environment's connection string.
_CONNECTION_VARS = {
    Env.DEV: "DB_CONNECTION_STRING_DEV",
    Env.UAT: "DB_CONNECTION_STRING_UAT",
    Env.PROD: "DB_CONNECTION_STRING_PROD",
}


def connection_string(env: Env) -> str:
    """The DB connection string for one environment, read from .env."""
    var = _CONNECTION_VARS[env]
    try:
        return os.environ[var]
    except KeyError:
        raise KeyError(f"Missing {var} in .env (required for --env {env.value}).")


EXCEL_WATCH_FOLDER = os.environ["EXCEL_WATCH_FOLDER"]