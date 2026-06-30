"""Model for DemandForecast.GpaFileDetail_tbl. Generated from the live DB.

GPA's per-file detail table. Raw rows from a GPA file land here.
"""
from datetime import date, time

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.types import Date, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class GpaFileDetail(Base):
    __tablename__ = "GpaFileDetail_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    FileDetailId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    FileId: Mapped[int] = mapped_column(ForeignKey("DemandForecast.File_tbl.FileId"))
    TERMINAL: Mapped[str | None] = mapped_column(NVARCHAR(100))
    WORK_DATE: Mapped[date | None] = mapped_column(Date)
    VESSEL: Mapped[str | None] = mapped_column(NVARCHAR(100))
    VOYAGE: Mapped[str | None] = mapped_column(NVARCHAR(100))
    LINE: Mapped[str | None] = mapped_column(NVARCHAR(100))
    SERVICE: Mapped[str | None] = mapped_column(NVARCHAR(100))
    FROM_PORT: Mapped[str | None] = mapped_column(NVARCHAR(100))
    TO_PORT: Mapped[str | None] = mapped_column(NVARCHAR(100))
    WORKTIME: Mapped[time | None] = mapped_column(Time)
    IM_FULL20: Mapped[int | None] = mapped_column(Integer)
    IM_FULL40: Mapped[int | None] = mapped_column(Integer)
    IM_FULL45: Mapped[int | None] = mapped_column(Integer)
    IM_MT: Mapped[int | None] = mapped_column(Integer)
    EX_FULL20: Mapped[int | None] = mapped_column(Integer)
    EX_FULL40: Mapped[int | None] = mapped_column(Integer)
    EX_MT: Mapped[int | None] = mapped_column(Integer)
    TOTAL: Mapped[int | None] = mapped_column(Integer)
    RAIL_IM20: Mapped[int | None] = mapped_column(Integer)
    RAIL_IM40: Mapped[int | None] = mapped_column(Integer)
    REPORTED: Mapped[str | None] = mapped_column(NVARCHAR(50))