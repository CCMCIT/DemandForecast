"""Model for DemandForecast.CmsStreetUseDaysDetail_tbl. Generated from the live DB.

CMS's per-file street-use-days detail table. Raw rows from a CMS file land here, with the
descriptive fields (out/in gate locations, equipment, ultimate user) still as text --
processing resolves them to FieldTypeValue ids in StreetUseDaysDetail_tbl.
"""
from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.types import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class CmsStreetUseDaysDetail(Base):
    __tablename__ = "CmsStreetUseDaysDetail_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    CmsStreetUseDaysDetailId: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    LoadId: Mapped[int] = mapped_column(ForeignKey("DemandForecast.Load_tbl.LoadId"))
    OutGateDate: Mapped[datetime] = mapped_column(DateTime)
    OutGateLocation: Mapped[str | None] = mapped_column(NVARCHAR(100))
    InGateDate: Mapped[datetime | None] = mapped_column(DateTime)
    InGateLocation: Mapped[str | None] = mapped_column(NVARCHAR(100))
    EquipmentCode: Mapped[str | None] = mapped_column(NVARCHAR(20))
    UltimateUser: Mapped[str | None] = mapped_column(NVARCHAR(100))
    CountOfRecords: Mapped[int | None] = mapped_column(Integer)
