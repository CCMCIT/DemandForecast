"""Model for DemandForecast.CmsOutOfServiceUnitsDetail_tbl. Generated from the live DB.

CMS's per-file out-of-service detail table. Raw rows from a CMS file land here, with the
descriptive fields (Equipment / Location) still as text -- processing resolves them to
FieldTypeValue ids in OutOfServiceUnitsDetail_tbl.
"""
from datetime import date

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.types import Date
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class CmsOutOfServiceUnitsDetail(Base):
    __tablename__ = "CmsOutOfServiceUnitsDetail_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    CmsOutOfServiceUnitsDetailId: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    LoadId: Mapped[int] = mapped_column(ForeignKey("DemandForecast.Load_tbl.LoadId"))
    Date: Mapped[date] = mapped_column(Date)
    EquipCode: Mapped[str | None] = mapped_column(NVARCHAR(50))
    LocationName: Mapped[str | None] = mapped_column(NVARCHAR(200))
    Units: Mapped[int | None] = mapped_column(Integer)
