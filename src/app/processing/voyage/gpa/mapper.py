"""Purpose: translate one GpaFileDetail row into a source-agnostic MappedVoyage.

This is the ONLY GPA-aware piece of processing. The column table is explicit
(no name-sniffing): each measure column becomes one VoyageDetails row with its
equipment type, direction, mode, and loaded flag. Equipment/Mode/Direction are
named here and resolved to ids by the writer, so this module needs no DB access
(Single Responsibility: mapping only). A new detail table adds its own mapper of
the same shape; the writer and runner are reused unchanged (Open/Closed).
"""
from app.lookups import FieldType
from app.processing.voyage.dto import MappedDetail, MappedVoyage
from app.processing.voyage.field_mapping import build_fields

# (GpaFileDetail column, equipment name, direction name, mode name, container loaded flag)
# The column names the container size -- IM_FULL20 is the 20-foot column -- so the
# equipment name is a property of the GPA format, not of any one database. The
# empties (MT) carry no equipment type. Names resolve to FieldTypeValue ids in the
# writer, against FieldType.EQUIPMENT_TYPE.
GPA_COLUMN_MAP = [
    ("IM_FULL20", "20CH", "Import", "Vessel", 1),
    ("IM_FULL40", "40CH", "Import", "Vessel", 1),
    ("IM_FULL45", "45CH", "Import", "Vessel", 1),
    ("IM_MT", None, "Import", "Vessel", 0),
    ("EX_FULL20", "20CH", "Export", "Vessel", 1),
    ("EX_FULL40", "40CH", "Export", "Vessel", 1),
    ("EX_MT", None, "Export", "Vessel", 0),
    ("RAIL_IM20", "20CH", "Import", "Rail", 0),
    ("RAIL_IM40", "40CH", "Import", "Rail", 0),
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
        file_id=detail.LoadId,
        voyage=detail.VOYAGE,
        work_date=detail.WORK_DATE,
        work_time=detail.WORKTIME,
        fields=build_fields(detail, GPA_FIELD_MAP),
    )
    for column, equipment, direction, mode, loaded in GPA_COLUMN_MAP:
        containers = getattr(detail, column)
        if not containers:
            continue  # empty (NULL) or zero column carries no data -> no VoyageDetails row
        voyage.details.append(
            MappedDetail(
                equipment_name=equipment,
                mode_name=mode,
                direction_name=direction,
                container_loaded_flag=loaded,
                containers=containers,
            )
        )
    return voyage