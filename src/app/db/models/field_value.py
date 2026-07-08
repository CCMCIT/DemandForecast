"""Model for DemandForecast.FieldValue_tbl. Generated from the live DB.

A shared pool of distinct raw string values (a vessel name, a port, a service, ...).
One row per distinct value, reused across types and voyages via FieldTypeValue_tbl.
"""
from sqlalchemy import Integer
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class FieldValue(Base):
    __tablename__ = "FieldValue_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    FieldValueId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    FieldValue: Mapped[str | None] = mapped_column(NVARCHAR(255))