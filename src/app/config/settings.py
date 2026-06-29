"""Application settings. DB url and paths come from .env."""
import os

from dotenv import load_dotenv

load_dotenv()

DB_CONNECTION_STRING = os.environ["DB_CONNECTION_STRING"]
EXCEL_WATCH_FOLDER = os.environ["EXCEL_WATCH_FOLDER"]
