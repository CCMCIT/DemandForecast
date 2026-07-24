"""Source-agnostic intermediate between the CMS mapper and the StreetUseDays writer.

The mapper turns one CmsStreetUseDaysDetail row into a MappedStreetUseDays: the two gate
dates and CountOfRecords copied as-is, and the four descriptive values (out/in gate
locations, equipment, ultimate user) carried as names. The writer resolves each name to a
FieldTypeValue id (via the upsert proc) and persists one StreetUseDaysDetail row -- a
straight 1:1 translation, no unpivot.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MappedStreetUseDays:
    file_id: int
    # OutGateDate is NOT NULL (business rule + DB); InGateDate may be absent.
    out_gate_date: datetime
    in_gate_date: datetime | None
    # Descriptive values carried as names; the writer resolves each to a FieldTypeValue id.
    og_location_name: str | None
    ig_location_name: str | None
    equip_code: str | None
    ultimate_user: str | None
    # Plain measure, copied straight through.
    count_of_records: int | None
