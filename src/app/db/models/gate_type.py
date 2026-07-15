"""Model for DemandForecast.GateType. Generated from the live DB. Lookup table.

The kind of gate move: 1 = In Gate, 2 = Out Gate.
"""
from sqlalchemy import Integer
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class GateType(Base):
    __tablename__ = "GateType"
    __table_args__ = {"schema": "DemandForecast"}

    GateTypeId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Name: Mapped[str] = mapped_column(NVARCHAR(50))