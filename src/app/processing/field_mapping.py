"""Source-agnostic helper: turn a source detail row into a list of MappedFields.

Each source declares its own spec -- a list of (FieldType, source column name) --
and this builds the MappedField list from it. GPA and any future source (FPA, ...)
reuse this unchanged; only the spec differs (Open/Closed). Blank/None values are
skipped, so they produce no FieldValue and no VoyageFieldMap row.
"""
from app.processing.dto import MappedField


def build_fields(row, spec) -> list[MappedField]:
    """spec = list of (FieldType, source column name) on `row`."""
    fields = []
    for field_type, column in spec:
        raw = getattr(row, column)
        value = raw.strip() if isinstance(raw, str) else raw
        if value:
            fields.append(MappedField(field_type_id=int(field_type), value=value))
    return fields