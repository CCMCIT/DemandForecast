"""Source-agnostic intermediate between the CMS mapper and the OutOfService writer.

The mapper turns one CmsOutOfServiceUnitsDetail row into a MappedOutOfService: Units copied
as-is and the two descriptive values (Equipment / Location) carried as names. The writer
resolves each name to a FieldTypeValue id (via the upsert proc) and persists one
OutOfServiceUnitsDetail row -- a straight 1:1 translation, no unpivot.
"""
from dataclasses import dataclass
from datetime import date


@dataclass
class MappedOutOfService:
    file_id: int
    date: date
    # Descriptive values carried as names; the writer resolves each to a FieldTypeValue id.
    equip_code: str | None
    location_name: str | None
    # Plain measure, copied straight through.
    units: int | None
