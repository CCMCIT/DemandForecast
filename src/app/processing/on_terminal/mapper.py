"""Purpose: translate one CmsOnTermDetail row into a MappedOnTerm.

This is the ONLY CMS-aware piece of on-terminal processing. It copies the plain measure
and carries the two descriptive values (Equipment / Location) as trimmed names -- the
writer resolves those to FieldTypeValue ids. No DB access here (Single Responsibility:
mapping only), so it is fully offline-testable.
"""
from app.processing.on_terminal.dto import MappedOnTerm


def map_row(detail) -> MappedOnTerm:
    return MappedOnTerm(
        file_id=detail.LoadId,
        date=detail.Date,
        equip_code=_clean(detail.EquipCode),
        location_name=_clean(detail.LocationName),
        units=detail.Units,
    )


def _clean(value: str | None) -> str | None:
    """Trim a descriptive name; treat blank/None as absent (no value to resolve).

    The FieldValue lookup is an exact string match, so trimming here prevents a padded
    name from creating a duplicate dimension row."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None
