"""Model for DemandForecast.AppLog_tbl. Generated from the live DB.

Shared, domain-neutral log sink. Written by every module (ingestion,
processing, future forecast). No FK to File_tbl on purpose: keeps the table
reusable so any module can be split into its own deployable later.
Source says which project wrote the row; ReferenceId is an optional,
FK-free correlation id (e.g. a FileId).
"""
from datetime import datetime

from sqlalchemy import Integer, text
from sqlalchemy.dialects.mssql import DATETIME2, NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class AppLog(Base):
    __tablename__ = "AppLog_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    LogId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Source: Mapped[str] = mapped_column(NVARCHAR(50))
    Level: Mapped[str] = mapped_column(NVARCHAR(20))
    Message: Mapped[str] = mapped_column(NVARCHAR(1000))
    Detail: Mapped[str | None] = mapped_column(NVARCHAR(None))  # NVARCHAR(MAX)
    ReferenceId: Mapped[int | None] = mapped_column(Integer)
    DateCreated: Mapped[datetime] = mapped_column(DATETIME2, server_default=text("getdate()"))