"""Purpose: translate one CmsGateActivityDetail row into a MappedGateActivity.

This is the ONLY CMS-aware piece of gate-activity processing. It copies the plain
measures, parses the gate type to its id, and carries the four descriptive values as
trimmed names -- the writer resolves those to FieldTypeValue ids. No DB access here
(Single Responsibility: mapping only), so it is fully offline-testable.
"""
from app.processing.gate_activity.dto import MappedGateActivity


def map_row(detail) -> MappedGateActivity:
    return MappedGateActivity(
        file_id=detail.LoadId,
        date=detail.Date,
        trucker_name=_clean(detail.TruckerName),
        equip_code=_clean(detail.EquipCode),
        ocean_carrier_name=_clean(detail.OceanCarrierName),
        location_name=_clean(detail.LocationName),
        equip_length=detail.EquipLength,
        length_match_id=detail.LengthMatchId,
        gate_type_id=_gate_type_id(detail.GateType),
        bare_chassis_flag=detail.BareChassisFlag,
        container_loaded_flag=detail.ContainerLoadedFlag,
        units=detail.Units,
        transactions=detail.Transactions,
    )


def _clean(value: str | None) -> str | None:
    """Trim a descriptive name; treat blank/None as absent (no value to resolve).

    The FieldValue lookup is an exact string match, so trimming here prevents a padded
    name from creating a duplicate dimension row."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _gate_type_id(value: str | None) -> int | None:
    """Parse the GateType column ('1' / '2') to its GateTypeId. Blank/None -> None.

    The value already IS the id as text, so this is a straight int() -- membership in
    the GateType lookup is checked later, against the DB, on the write path."""
    if value is None:
        return None
    trimmed = value.strip()
    return int(trimmed) if trimmed else None