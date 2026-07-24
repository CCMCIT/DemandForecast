"""Unit test (no DB): the CMS mapper turns a CmsStreetUseDaysDetail row into a
MappedStreetUseDays -- copies both gate dates and CountOfRecords, carries and trims the
four descriptive names (out/in gate location, equipment, ultimate user)."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.processing.street_use_days.mapper import map_row

pytestmark = pytest.mark.unit


def _detail(**overrides):
    """A minimal stand-in for a CmsStreetUseDaysDetail row."""
    base = dict(
        LoadId=7,
        OutGateDate=datetime(2026, 1, 14, 8, 0),
        InGateDate=datetime(2026, 1, 20, 17, 30),
        OutGateLocation="GPA - Garden City 3.0",
        InGateLocation="GPA - Ocean Terminal",
        EquipmentCode="40STR",
        UltimateUser="MAERSK",
        CountOfRecords=3,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_dates_and_measure_are_copied():
    m = map_row(_detail())
    assert m.file_id == 7
    assert m.out_gate_date == datetime(2026, 1, 14, 8, 0)
    assert m.in_gate_date == datetime(2026, 1, 20, 17, 30)
    assert m.count_of_records == 3


def test_descriptive_names_are_carried():
    m = map_row(_detail())
    assert m.og_location_name == "GPA - Garden City 3.0"
    assert m.ig_location_name == "GPA - Ocean Terminal"
    assert m.equip_code == "40STR"
    assert m.ultimate_user == "MAERSK"


def test_names_are_trimmed():
    m = map_row(_detail(
        OutGateLocation="  GPA - Garden City 3.0  ",
        InGateLocation=" GPA - Ocean Terminal ",
        EquipmentCode=" 40STR ",
        UltimateUser="  MAERSK ",
    ))
    assert m.og_location_name == "GPA - Garden City 3.0"
    assert m.ig_location_name == "GPA - Ocean Terminal"
    assert m.equip_code == "40STR"
    assert m.ultimate_user == "MAERSK"


def test_blank_and_none_names_become_none():
    m = map_row(_detail(
        OutGateLocation="   ", InGateLocation=None,
        EquipmentCode=None, UltimateUser="  ",
    ))
    assert m.og_location_name is None
    assert m.ig_location_name is None
    assert m.equip_code is None
    assert m.ultimate_user is None


def test_null_count_passes_through_as_none():
    assert map_row(_detail(CountOfRecords=None)).count_of_records is None


def test_null_in_gate_date_passes_through_as_none():
    assert map_row(_detail(InGateDate=None)).in_gate_date is None
