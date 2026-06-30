"""Model for DemandForecast.Direction_tbl. Generated from the live DB. Lookup table."""
from sqlalchemy import Integer
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Direction(Base):
    __tablename__ = "Direction_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    DirectionId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    DirectionName: Mapped[str | None] = mapped_column(NVARCHAR(100))