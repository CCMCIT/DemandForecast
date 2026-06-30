"""Model for DemandForecast.Mode_tbl. Generated from the live DB. Lookup table."""
from sqlalchemy import Integer
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Mode(Base):
    __tablename__ = "Mode_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    ModeId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ModeName: Mapped[str | None] = mapped_column(NVARCHAR(100))
    Description: Mapped[str | None] = mapped_column(NVARCHAR(255))