"""Model for DemandForecast.FieldTypeValue_tbl. Generated from the live DB.

One (FieldType, FieldValue) pairing -- e.g. Equipment Type + '20CH'. Its id is what
VoyageDetails.FieldTypeValueEquipTypeId and the field-map tables point at.

Rows are created by the DB (DemandForecast.VoyageFieldMap_upsert); the app only
reads them. ExternalId is filled in later by FieldTypeValueExternalId_resolve.
"""
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.mssql import BIT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class FieldTypeValue(Base):
    __tablename__ = "FieldTypeValue_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    FieldTypeValueId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # DB-level FK to FieldType_tbl (lookup not mapped in the ORM): plain Integer.
    FieldTypeId: Mapped[int] = mapped_column(Integer)
    FieldValueId: Mapped[int] = mapped_column(
        ForeignKey("DemandForecast.FieldValue_tbl.FieldValueId")
    )
    ExternalId: Mapped[int | None] = mapped_column(Integer)
    ExternalNotifFlag: Mapped[bool | None] = mapped_column(BIT)