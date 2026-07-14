"""Purpose: translate one GpaFileDetail row into a source-agnostic MappedVoyage.

This is the ONLY GPA-aware piece of processing. The column table is explicit
(no name-sniffing): each measure column becomes one VoyageDetails row with its
FieldTypeValueEquipTypeId, direction, mode, and loaded flag. Mode/Direction are
named here and resolved to ids by the writer, so this module needs no DB access
(Single Responsibility: mapping only). A new detail table adds its own mapper of
the same shape; the writer and runner are reused unchanged (Open/Closed).
"""
from app.lookups import FieldType
from app.processing.dto import MappedDetail, MappedVoyage
from app.processing.field_mapping import build_fields

# (GpaFileDetail column, FieldTypeValueEquipTypeId, direction name, mode name, container loaded flag)
# FieldTypeValueEquipTypeId encodes the container size: 20CH -> 1, 40CH -> 2, 45CH -> 3,
# and the empties (MT) -> None.
GPA_COLUMN_MAP = [
    ("IM_FULL20", 1, "Import", "Vessel", 1),
    ("IM_FULL40", 2, "Import", "Vessel", 1),
    ("IM_FULL45", 3, "Import", "Vessel", 1),
    ("IM_MT", None, "Import", "Vessel", 0),
    ("EX_FULL20", 1, "Export", "Vessel", 1),
    ("EX_FULL40", 2, "Export", "Vessel", 1),
    ("EX_MT", None, "Export", "Vessel", 0),
    ("RAIL_IM20", 1, "Import", "Rail", 0),
    ("RAIL_IM40", 2, "Import", "Rail", 0),
]

# (FieldType, GpaFileDetail column) -> the voyage's descriptive fields. Each becomes
# one FieldValue/FieldTypeValue and a VoyageFieldMap row (see processing.writer).
GPA_FIELD_MAP = [
    (FieldType.VESSEL, "VESSEL"),
    (FieldType.OCEAN_CARRIER, "LINE"),
    (FieldType.SERVICE, "SERVICE"),
    (FieldType.LOCATION, "TERMINAL"),
    (FieldType.ORIGIN_PORT, "FROM_PORT"),
    (FieldType.DESTINATION_PORT, "TO_PORT"),
]


def map_row(detail) -> MappedVoyage:
    voyage = MappedVoyage(
        file_id=detail.FileId,
        voyage=detail.VOYAGE,
        work_date=detail.WORK_DATE,
        work_time=detail.WORKTIME,
        fields=build_fields(detail, GPA_FIELD_MAP),
    )
    for column, field_type_value_id, direction, mode, loaded in GPA_COLUMN_MAP:
        containers = getattr(detail, column)
        if not containers:
            continue  # empty (NULL) or zero column carries no data -> no VoyageDetails row
        voyage.details.append(
            MappedDetail(
                field_type_value_id=field_type_value_id,
                mode_name=mode,
                direction_name=direction,
                container_loaded_flag=loaded,
                containers=containers,
            )
        )
    return voyage