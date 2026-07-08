"""Repository for FieldTypeValue_tbl (shared dimension).

Get-or-create by (FieldTypeId, FieldValueId), with existing rows preloaded into a
cache once per instance. ExternalId/ExternalNotifFlag are left NULL here; resolving
them against external master tables is a separate, later concern.
"""
from app.db.models.field_type_value import FieldTypeValue


class FieldTypeValueRepository:
    def __init__(self, session):
        self.session = session
        self._ids = {
            (r.FieldTypeId, r.FieldValueId): r.FieldTypeValueId
            for r in session.query(FieldTypeValue).all()
        }

    def get_or_create_id(self, field_type_id: int, field_value_id: int) -> int:
        """Id of the FieldTypeValue pairing this type and value, inserting it once
        if new."""
        key = (field_type_id, field_value_id)
        if key not in self._ids:
            row = FieldTypeValue(FieldTypeId=field_type_id, FieldValueId=field_value_id)
            self.session.add(row)
            self.session.flush()  # assign the identity FieldTypeValueId
            self._ids[key] = row.FieldTypeValueId
        return self._ids[key]