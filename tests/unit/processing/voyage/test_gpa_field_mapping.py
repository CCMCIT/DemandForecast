"""Unit test (no DB): the GPA mapper turns the 6 descriptive columns into
MappedFields with the right FieldType, trims values, and skips blank/None."""
from datetime import date, time
from types import SimpleNamespace

import pytest

from app.lookups import FieldType
from app.processing.voyage.gpa.mapper import map_row

pytestmark = pytest.mark.unit


def _detail(**overrides):
    """A minimal stand-in for a GpaFileDetail row. Measure columns default to None
    so map_row produces no VoyageDetails -- these tests only assert on fields."""
    base = dict(
        FileId=1, VOYAGE="FX123", WORK_DATE=date(2025, 7, 4), WORKTIME=time(0, 0),
        TERMINAL="GCT Bayonne", VESSEL="MSC ISABELLA", LINE="MSC", SERVICE="AE7",
        FROM_PORT="Ningbo", TO_PORT="New York",
        IM_FULL20=None, IM_FULL40=None, IM_FULL45=None, IM_MT=None,
        EX_FULL20=None, EX_FULL40=None, EX_MT=None, RAIL_IM20=None, RAIL_IM40=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_six_fields_mapped_to_correct_types():
    voyage = map_row(_detail())
    assert {(f.field_type_id, f.value) for f in voyage.fields} == {
        (FieldType.VESSEL, "MSC ISABELLA"),
        (FieldType.OCEAN_CARRIER, "MSC"),
        (FieldType.SERVICE, "AE7"),
        (FieldType.LOCATION, "GCT Bayonne"),
        (FieldType.ORIGIN_PORT, "Ningbo"),
        (FieldType.DESTINATION_PORT, "New York"),
    }


def test_values_are_trimmed():
    voyage = map_row(_detail(VESSEL="  MSC ISABELLA  "))
    vessel = next(f for f in voyage.fields if f.field_type_id == FieldType.VESSEL)
    assert vessel.value == "MSC ISABELLA"


def test_blank_and_none_values_are_skipped():
    voyage = map_row(_detail(SERVICE="   ", TO_PORT=None))
    present = {f.field_type_id for f in voyage.fields}
    assert FieldType.SERVICE not in present
    assert FieldType.DESTINATION_PORT not in present
    assert len(voyage.fields) == 4