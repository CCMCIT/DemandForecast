"""Purpose: translate one CmsStreetUseDaysDetail row into a MappedStreetUseDays.

This is the ONLY CMS-aware piece of street-use-days processing. It copies the two gate dates
and the measure, and carries the four descriptive values (out/in gate locations, equipment,
ultimate user) as trimmed names -- the writer resolves those to FieldTypeValue ids. No DB
access here (Single Responsibility: mapping only), so it is fully offline-testable.
"""
from app.processing.street_use_days.dto import MappedStreetUseDays


def map_row(detail) -> MappedStreetUseDays:
    return MappedStreetUseDays(
        file_id=detail.LoadId,
        out_gate_date=detail.OutGateDate,
        in_gate_date=detail.InGateDate,
        og_location_name=_clean(detail.OutGateLocation),
        ig_location_name=_clean(detail.InGateLocation),
        equip_code=_clean(detail.EquipmentCode),
        ultimate_user=_clean(detail.UltimateUser),
        count_of_records=detail.CountOfRecords,
    )


def _clean(value: str | None) -> str | None:
    """Trim a descriptive name; treat blank/None as absent (no value to resolve).

    The FieldValue lookup is an exact string match, so trimming here prevents a padded
    name from creating a duplicate dimension row."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None
