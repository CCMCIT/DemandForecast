"""Declarative base for generated/reflected models.

Never used to create or alter schema. The DB owns the schema.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
