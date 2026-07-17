"""Model for DemandForecast.Load_tbl. Generated from the live DB. Shared by all companies.

LoadTypeId and LoadStatusId are FKs into the FileType_tbl / LoadStatus_tbl lookups
(see app.lookups for the mirrored ids).
"""
from datetime import datetime

from sqlalchemy import Integer, text
from sqlalchemy.dialects.mssql import DATETIME2, NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Load(Base):
    __tablename__ = "Load_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    LoadId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    SourceName: Mapped[str | None] = mapped_column(NVARCHAR(255))
    DateLoaded: Mapped[datetime] = mapped_column(DATETIME2, server_default=text("getdate()"))
    # LoadTypeId / LoadStatusId are DB-level FKs to FileType_tbl / LoadStatus_tbl.
    # Those lookups aren't mapped in the ORM, so they stay plain Integer columns
    # (the DB still enforces the constraints). See app.lookups for the ids.
    LoadTypeId: Mapped[int | None] = mapped_column(Integer)
    LoadStatusId: Mapped[int | None] = mapped_column(Integer)