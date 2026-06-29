"""Engine and session factory. The DB owns the schema; we never create or alter it."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import DB_CONNECTION_STRING

engine = create_engine(DB_CONNECTION_STRING)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
