"""Source-agnostic intermediate between the CMS mapper and the GateActivity writer.

The mapper turns one CmsGateActivityDetail row into a MappedGateActivity: the plain
measures copied as-is, the gate type parsed to its id, and the four descriptive values
carried as names. The writer resolves each name to a FieldTypeValue id (via the upsert
proc) and persists one GateActivityDetail row -- a straight 1:1 translation, no unpivot.
"""
from dataclasses import dataclass
from datetime import date


@dataclass
class MappedGateActivity:
    file_id: int
    date: date
    # Descriptive values carried as names; the writer resolves each to a FieldTypeValue id.
    trucker_name: str | None
    equip_code: str | None
    ocean_carrier_name: str | None
    location_name: str | None
    # Plain measures, copied straight through.
    equip_length: int | None
    length_match: bool | None
    gate_type_id: int | None
    bare_chassis_flag: bool | None
    container_loaded_flag: bool | None
    units: int | None
    transactions: int | None
