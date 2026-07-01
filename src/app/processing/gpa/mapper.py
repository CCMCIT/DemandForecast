"""Purpose: translate one GpaFileDetail row into a source-agnostic MappedVoyage.

This is the ONLY GPA-aware piece of processing. The column table is explicit
(no name-sniffing): each measure column becomes one VoyageDetails row with its
FieldTypeValueEquipTypeId, direction, mode, and loaded flag. Mode/Direction are
named here and resolved to ids by the writer, so this module needs no DB access
(Single Responsibility: mapping only). A new detail table adds its own mapper of
the same shape; the writer and runner are reused unchanged (Open/Closed).
"""
from app.processing.dto import MappedDetail, MappedVoyage

# (GpaFileDetail column, FieldTypeValueEquipTypeId, direction name, mode name, container loaded flag)
# FieldTypeValueEquipTypeId encodes the container size: 20 -> 1, 40 -> 2, 45 -> 3,
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


def map_row(detail) -> MappedVoyage:
    voyage = MappedVoyage(
        file_id=detail.FileId,
        voyage=detail.VOYAGE,
        work_date=detail.WORK_DATE,
        work_time=detail.WORKTIME,
    )
    for column, field_type_value_id, direction, mode, loaded in GPA_COLUMN_MAP:
        voyage.details.append(
            MappedDetail(
                field_type_value_id=field_type_value_id,
                mode_name=mode,
                direction_name=direction,
                container_loaded_flag=loaded,
                containers=getattr(detail, column),
            )
        )
    return voyage