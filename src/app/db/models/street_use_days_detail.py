"""Model for DemandForecast.StreetUseDaysDetail_tbl. Generated from the live DB.

The processed street-use-days target: one row per CMS staging row (1:1, no unpivot). The
descriptive fields are resolved to FieldTypeValue ids here (out/in gate locations, equipment
type, ocean carrier). Out/In gate dates and CountOfRecords are copied straight through.

A row's identity is the 6 descriptive columns (out/in gate dates + the four FieldTypeValue
ids); the DB enforces it via UQ_StreetUseDaysDetail_Identity. LoadId and CountOfRecords are
the mutable payload.

The FieldTypeValue*Id columns are plain Integer: the DB has no FK on them, so the ORM
mirrors that (do not invent constraints the DB does not have).
"""
from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.types import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class StreetUseDaysDetail(Base):
    __tablename__ = "StreetUseDaysDetail_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    StreetUseDaysDetailId: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    LoadId: Mapped[int] = mapped_column(ForeignKey("DemandForecast.Load_tbl.LoadId"))
    OutGateDate: Mapped[datetime] = mapped_column(DateTime)
    FieldTypeValueOGLocationId: Mapped[int | None] = mapped_column(Integer)
    InGateDate: Mapped[datetime | None] = mapped_column(DateTime)
    FieldTypeValueIGLocationId: Mapped[int | None] = mapped_column(Integer)
    FieldTypeValueEquipTypeId: Mapped[int | None] = mapped_column(Integer)
    FieldTypeValueOceanCarrierId: Mapped[int | None] = mapped_column(Integer)
    CountOfRecords: Mapped[int | None] = mapped_column(Integer)
