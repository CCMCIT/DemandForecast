"""Unit test (no DB): the CMS mapper turns a CmsOnTermDetail row into a
MappedOnTerm -- copies Units, carries and trims the Equipment/Location names."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.processing.on_terminal.mapper import map_row

pytestmark = pytest.mark.unit


def _detail(**overrides):
    """A minimal stand-in for a CmsOnTermDetail row."""
    base = dict(
        LoadId=7, Date=date(2026, 1, 14),
        EquipCode="40STR", LocationName="GPA - Garden City 3.0",
        Units=3,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_plain_measures_are_copied():
    m = map_row(_detail())
    assert (m.file_id, m.date) == (7, date(2026, 1, 14))
    assert m.units == 3


def test_descriptive_names_are_carried():
    m = map_row(_detail())
    assert m.equip_code == "40STR"
    assert m.location_name == "GPA - Garden City 3.0"


def test_names_are_trimmed():
    m = map_row(_detail(EquipCode=" 40STR ", LocationName="  GPA - Garden City 3.0  "))
    assert m.equip_code == "40STR"
    assert m.location_name == "GPA - Garden City 3.0"


def test_blank_and_none_names_become_none():
    m = map_row(_detail(EquipCode=None, LocationName="   "))
    assert m.equip_code is None
    assert m.location_name is None


def test_null_units_passes_through_as_none():
    assert map_row(_detail(Units=None)).units is None