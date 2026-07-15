"""Model for DemandForecast.CmsGateActivityDetail_tbl. Generated from the live DB.

CMS's per-file gate-activity detail table. Raw rows from a CMS file land here, with
the descriptive fields (Trucker / Equipment / Ocean Carrier / Location / Gate Type)
still as text -- processing resolves them to ids in GateActivityDetail_tbl.

The '_naum' in the table name is a temporary marker; only __tablename__ carries it,
so swapping to the final 'CmsGateActivityDetail_tbl' is a one-line change here.
"""
from datetime import date

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.mssql import BIT, NVARCHAR
from sqlalchemy.types import Date
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class CmsGateActivityDetail(Base):
    __tablename__ = "CmsGateActivityDetail_naum_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    CmsGateActivityDetailId: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    FileId: Mapped[int] = mapped_column(ForeignKey("DemandForecast.File_tbl.FileId"))
    Date: Mapped[date] = mapped_column(Date)
    TruckerName: Mapped[str | None] = mapped_column(NVARCHAR(200))
    EquipCode: Mapped[str | None] = mapped_column(NVARCHAR(50))
    EquipLength: Mapped[int | None] = mapped_column(Integer)
    LengthMatch: Mapped[bool | None] = mapped_column(BIT)
    OceanCarrierName: Mapped[str | None] = mapped_column(NVARCHAR(200))
    GateType: Mapped[str | None] = mapped_column(NVARCHAR(100))
    BareChassisFlag: Mapped[bool | None] = mapped_column(BIT)
    ContainerLoadedFlag: Mapped[bool | None] = mapped_column(BIT)
    LocationName: Mapped[str | None] = mapped_column(NVARCHAR(200))
    Units: Mapped[int | None] = mapped_column(Integer)
    Transactions: Mapped[int | None] = mapped_column(Integer)