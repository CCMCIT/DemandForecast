"""Model for DemandForecast.VoyageDetails_tbl. Generated from the live DB.

Shared target. Many rows per Voyage (1:M), one per mapped source measure.
"""
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.mssql import BIT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class VoyageDetails(Base):
    __tablename__ = "VoyageDetails_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    VoyageDetailsId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    VoyageId: Mapped[int] = mapped_column(ForeignKey("DemandForecast.Voyage_tbl.VoyageId"))
    # DB-level FK to FieldTypeValue_tbl (lookup not mapped in the ORM): plain Integer.
    FieldTypeValueEquipTypeId: Mapped[int | None] = mapped_column(Integer)
    ModeId: Mapped[int | None] = mapped_column(ForeignKey("DemandForecast.Mode_tbl.ModeId"))
    DirectionId: Mapped[int | None] = mapped_column(
        ForeignKey("DemandForecast.Direction_tbl.DirectionId")
    )
    ContainerLoadedFlag: Mapped[bool | None] = mapped_column(BIT)
    Containers: Mapped[int | None] = mapped_column(Integer)