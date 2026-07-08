"""Model for DemandForecast.FieldTypeValue_tbl. Generated from the live DB.

Pairs a FieldType with a FieldValue into one typed value (e.g. Vessel + 'MSC
ISABELLA'). ExternalId/ExternalNotifFlag support resolving that value to an id in
an external master table; the current pipeline leaves them NULL.

FieldTypeId / FieldValueId are DB-level FKs to FieldType_tbl / FieldValue_tbl. Those
targets aren't guaranteed loaded in the ORM path, so they stay plain Integer columns
(the DB still enforces the constraints) -- same convention as
VoyageDetails.FieldTypeValueEquipTypeId.
"""
from sqlalchemy import Integer
from sqlalchemy.dialects.mssql import BIT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class FieldTypeValue(Base):
    __tablename__ = "FieldTypeValue_tbl"
    __table_args__ = {"schema": "DemandForecast"}

    FieldTypeValueId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    FieldTypeId: Mapped[int] = mapped_column(Integer)
    FieldValueId: Mapped[int] = mapped_column(Integer)
    ExternalId: Mapped[int | None] = mapped_column(Integer)
    ExternalNotifFlag: Mapped[bool | None] = mapped_column(BIT)