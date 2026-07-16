"""Unit test (no DB): the GPA mapper names each measure column's equipment type
instead of hardcoding a FieldTypeValue id.

The name comes from the column -- IM_FULL20 is the 20-foot column -- so it is a fact
about the GPA format, true in every environment. The id it resolves to is a fact about
one database, and belongs to the writer's lookup, not to the mapper.
"""
from datetime import date, time
from types import SimpleNamespace

import pytest

from app.processing.voyage.gpa.mapper import GPA_COLUMN_MAP, map_row

pytestmark = pytest.mark.unit


def _detail(**overrides):
    """A minimal stand-in for a GpaFileDetail row. Measure columns default to None, so
    only the ones a test sets produce a detail."""
    base = dict(
        FileId=1, VOYAGE="FX123", WORK_DATE=date(2025, 7, 4), WORKTIME=time(0, 0),
        TERMINAL=None, VESSEL=None, LINE=None, SERVICE=None,
        FROM_PORT=None, TO_PORT=None,
        IM_FULL20=None, IM_FULL40=None, IM_FULL45=None, IM_MT=None,
        EX_FULL20=None, EX_FULL40=None, EX_MT=None, RAIL_IM20=None, RAIL_IM40=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_container_columns_carry_their_equipment_name():
    voyage = map_row(_detail(IM_FULL20=5, IM_FULL40=6, IM_FULL45=7))
    assert [(d.equipment_name, d.containers) for d in voyage.details] == [
        ("20CH", 5),
        ("40CH", 6),
        ("45CH", 7),
    ]


def test_export_columns_carry_the_same_names_as_import():
    voyage = map_row(_detail(EX_FULL20=1, EX_FULL40=2))
    assert [(d.equipment_name, d.direction_name) for d in voyage.details] == [
        ("20CH", "Export"),
        ("40CH", "Export"),
    ]


def test_rail_columns_carry_the_same_names_as_vessel():
    voyage = map_row(_detail(RAIL_IM20=1, RAIL_IM40=2))
    assert [(d.equipment_name, d.mode_name) for d in voyage.details] == [
        ("20CH", "Rail"),
        ("40CH", "Rail"),
    ]


def test_empties_carry_no_equipment_name():
    voyage = map_row(_detail(IM_MT=3, EX_MT=4))
    assert [d.equipment_name for d in voyage.details] == [None, None]


def test_column_map_names_equipment_never_carries_a_database_id():
    """Regression guard on the table itself. A FieldTypeValueId is an environment-
    assigned identity value; putting one back here would silently bind the mapper to
    one database again, which is exactly what this change removed."""
    for column, equipment, *_ in GPA_COLUMN_MAP:
        assert equipment is None or isinstance(equipment, str), (
            f"{column} carries {equipment!r}: the column map must name the equipment, "
            f"not carry its id"
        )