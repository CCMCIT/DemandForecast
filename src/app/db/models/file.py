"""Model for DemandForecast.File_tbl. Generated from the live DB. Shared by all companies."""
from datetime import datetime

from sqlalchemy import Integer, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class File(Base):
    __tablename__ = "File_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    FileId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    FileName: Mapped[str | None] = mapped_column(NVARCHAR(255))
    DateLoaded: Mapped[datetime] = mapped_column(DATETIME2, server_default=text("getdate()"))
    FileType: Mapped[str | None] = mapped_column(NVARCHAR(50))
    LoadStatus: Mapped[bool] = mapped_column(BIT, server_default=text("0"))