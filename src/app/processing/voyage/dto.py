"""Source-agnostic intermediate between a company mapper and the Voyage writer.

A mapper turns one source detail row into a MappedVoyage (the Voyage fields plus
its VoyageDetails rows). The writer consumes this without knowing the source.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time


@dataclass
class MappedDetail:
    """One measure of a voyage. Equipment/Mode/Direction are carried by name; the
    writer resolves each to its id, so mappers stay free of database ids."""
    equipment_name: str | None   # e.g. '20CH'; None for empties (no equipment type)
    mode_name: str
    direction_name: str
    container_loaded_flag: int
    containers: int | None


@dataclass
class MappedField:
    """One typed descriptive value of a voyage (e.g. Vessel = 'MSC ISABELLA').
    Source-agnostic: any source maps its columns to these, the writer persists them."""
    field_type_id: int
    value: str


@dataclass
class MappedVoyage:
    file_id: int
    voyage: str
    work_date: date | None
    work_time: time | None
    reported: datetime | None   # when the voyage was last reported; None if blank/unreadable
    details: list[MappedDetail] = field(default_factory=list)
    fields: list[MappedField] = field(default_factory=list)