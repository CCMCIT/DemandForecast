"""Model for DemandForecast.VoyageFieldMap_tbl. Generated from the live DB.

Links a Voyage to its typed field values: many rows per voyage, one per field
type present on the source row (Vessel, Ocean Carrier, Service, Location, ...).
"""
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class VoyageFieldMap(Base):
    __tablename__ = "VoyageFieldMap_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    MapId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    VoyageId: Mapped[int] = mapped_column(ForeignKey("DemandForecast.Voyage_tbl.VoyageId"))
    # DB-level FK to FieldTypeValue_tbl (lookup not loaded in the ORM path): plain
    # Integer, same convention as VoyageDetails.FieldTypeValueEquipTypeId.
    FieldTypeValueId: Mapped[int] = mapped_column(Integer)