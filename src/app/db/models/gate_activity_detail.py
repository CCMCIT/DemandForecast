"""Model for DemandForecast.GateActivityDetail_tbl. Generated from the live DB.

The processed gate-activity target: one row per CMS staging row (1:1, no unpivot).
The descriptive fields are resolved to FieldTypeValue ids here; Gate Type to its
lookup id. GateActivityStatusId is left NULL for now (no source yet).

The FieldTypeValue*Id / GateTypeId columns are plain Integer: the DB has no FK on
them, so the ORM mirrors that (do not invent constraints the DB does not have).
"""
from datetime import date

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.mssql import BIT
from sqlalchemy.types import Date
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class GateActivityDetail(Base):
    __tablename__ = "GateActivityDetail_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    GateActivityDetailId: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    FileId: Mapped[int] = mapped_column(ForeignKey("DemandForecast.File_tbl.FileId"))
    Date: Mapped[date] = mapped_column(Date)
    FieldTypeValueTruckerId: Mapped[int | None] = mapped_column(Integer)
    FieldTypeValueEquipTypeId: Mapped[int | None] = mapped_column(Integer)
    EquipLength: Mapped[int | None] = mapped_column(Integer)
    LengthMatch: Mapped[bool | None] = mapped_column(BIT)
    FieldTypeValueOceanCarrierId: Mapped[int | None] = mapped_column(Integer)
    GateTypeId: Mapped[int | None] = mapped_column(Integer)
    BareChassisFlag: Mapped[bool | None] = mapped_column(BIT)
    ContainerLoadedFlag: Mapped[bool | None] = mapped_column(BIT)
    FieldTypeValueLocationId: Mapped[int | None] = mapped_column(Integer)
    Units: Mapped[int | None] = mapped_column(Integer)
    Transactions: Mapped[int | None] = mapped_column(Integer)
    GateActivityStatusId: Mapped[int | None] = mapped_column(Integer)