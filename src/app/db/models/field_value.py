"""Model for DemandForecast.FieldValue_tbl. Generated from the live DB.

The raw text of a descriptive value ('MSC ISABELLA', '20CH', ...), independent of
which FieldType uses it. FieldTypeValue_tbl pairs it with a type.
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