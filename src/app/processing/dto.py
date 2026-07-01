"""Source-agnostic intermediate between a company mapper and the Voyage writer.

A mapper turns one source detail row into a MappedVoyage (the Voyage fields plus
its VoyageDetails rows). The writer consumes this without knowing the source.
"""
from dataclasses import dataclass, field
from datetime import date, time


@dataclass
class MappedDetail:
    field_type_value_id: int | None
    mode_name: str
    direction_name: str
    container_loaded_flag: int
    containers: int | None


@dataclass
class MappedVoyage:
    file_id: int
    voyage: str
    work_date: date | None
    work_time: time | None
    details: list[MappedDetail] = field(default_factory=list)