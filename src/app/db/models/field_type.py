"""Model for DemandForecast.FieldType_tbl. Generated from the live DB. Lookup table.

The static set of field types a voyage can be tagged with (Vessel, Ocean Carrier,
...). Row 1 (Equipment Type) is also referenced by VoyageDetails. The External*
columns describe how a value could be resolved to an id in an external master
table; the current pipeline does not use them (see FieldTypeValue.ExternalId).
"""
from sqlalchemy import Integer
from sqlalchemy.dialects.mssql import BIT, NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class FieldType(Base):
    __tablename__ = "FieldType_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    FieldTypeId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    FieldType: Mapped[str | None] = mapped_column(NVARCHAR(100))
    ExternalTableName: Mapped[str | None] = mapped_column(NVARCHAR(128))
    ExternalColumnName: Mapped[str | None] = mapped_column(NVARCHAR(128))
    ExternalNotifFlag: Mapped[bool | None] = mapped_column(BIT)
    ExternalIdColumn: Mapped[str | None] = mapped_column(NVARCHAR(255))
    ExternalWhereClause: Mapped[str | None] = mapped_column(NVARCHAR)  # NVARCHAR(MAX)
