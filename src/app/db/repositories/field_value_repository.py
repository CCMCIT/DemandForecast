"""Repository for FieldValue_tbl (shared dimension).

Get-or-create by value, with the existing rows preloaded into an in-memory cache
once per instance (same pattern as ModeRepository/DirectionRepository). This keeps
processing a file to a single up-front query instead of one lookup per row, and
dedupes repeated values within the run.
"""
from app.db.models.field_value import FieldValue


class FieldValueRepository:
    def __init__(self, session):
        self.session = session
        self._ids = {v.FieldValue: v.FieldValueId for v in session.query(FieldValue).all()}

    def get_or_create_id(self, value: str) -> int:
        """Id of the FieldValue for `value`, inserting it once if new. `value` is
        expected already trimmed by the caller."""
        if value not in self._ids:
            row = FieldValue(FieldValue=value)
            self.session.add(row)
            self.session.flush()  # assign the identity FieldValueId
            self._ids[value] = row.FieldValueId
        return self._ids[value]