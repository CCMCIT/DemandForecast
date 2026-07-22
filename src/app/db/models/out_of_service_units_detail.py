"""Model for DemandForecast.OutOfServiceUnitsDetail_tbl. Generated from the live DB.

The processed out-of-service target: one row per CMS staging row (1:1, no unpivot). The
descriptive fields are resolved to FieldTypeValue ids here (Equipment / Location).

The FieldTypeValue*Id columns are plain Integer: the DB has no FK on them, so the ORM
mirrors that (do not invent constraints the DB does not have).
"""
from datetime import date

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.types import Date
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class OutOfServiceUnitsDetail(Base):
    __tablename__ = "OutOfServiceUnitsDetail_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    OutOfServiceUnitsDetailId: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    LoadId: Mapped[int] = mapped_column(ForeignKey("DemandForecast.Load_tbl.LoadId"))
    Date: Mapped[date] = mapped_column(Date)
    FieldTypeValueEquipTypeId: Mapped[int | None] = mapped_column(Integer)
    FieldTypeValueLocationId: Mapped[int | None] = mapped_column(Integer)
    Units: Mapped[int | None] = mapped_column(Integer)
