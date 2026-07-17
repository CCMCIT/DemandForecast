"""Model for DemandForecast.Voyage_tbl. Generated from the live DB.

Shared target for all companies. One Voyage row per source detail row.
"""
from datetime import date, time

from sqlalchemy import ForeignKey, Integer, text
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.types import Date, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Voyage(Base):
    __tablename__ = "Voyage_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    VoyageId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    LoadId: Mapped[int] = mapped_column(ForeignKey("DemandForecast.Load_tbl.LoadId"))
    Voyage: Mapped[str] = mapped_column(NVARCHAR(100))
    WORK_DATE: Mapped[date | None] = mapped_column(Date)
    WorkTime: Mapped[time | None] = mapped_column(Time)
    # DB-level FK to VoyageStatus_tbl (lookup mirrored in app.lookups.VoyageStatus).
    # Server default 1 (ToCall); the writer also sets it explicitly on every write.
    VoyageStatusId: Mapped[int] = mapped_column(Integer, server_default=text("1"))