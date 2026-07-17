"""Unit test (no DB): the CMS mapper turns a CmsGateActivityDetail row into a
MappedGateActivity -- copies the measures, parses the gate type, trims the names."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.processing.gate_activity.mapper import map_row

pytestmark = pytest.mark.unit


def _detail(**overrides):
    """A minimal stand-in for a CmsGateActivityDetail row."""
    base = dict(
        LoadId=7, Date=date(2026, 1, 14),
        TruckerName="All Points Transport", EquipCode="40STR",
        OceanCarrierName="Maersk A/S", LocationName="GPA - Garden City 3.0",
        EquipLength=40, LengthMatchId=1, GateType="1",
        BareChassisFlag=False, ContainerLoadedFlag=True,
        Units=3, Transactions=2,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_plain_measures_are_copied():
    m = map_row(_detail())
    assert (m.file_id, m.date) == (7, date(2026, 1, 14))
    assert (m.equip_length, m.length_match_id) == (40, 1)
    assert (m.bare_chassis_flag, m.container_loaded_flag) == (False, True)
    assert (m.units, m.transactions) == (3, 2)


def test_descriptive_names_are_carried():
    m = map_row(_detail())
    assert m.trucker_name == "All Points Transport"
    assert m.equip_code == "40STR"
    assert m.ocean_carrier_name == "Maersk A/S"
    assert m.location_name == "GPA - Garden City 3.0"


def test_gate_type_text_is_parsed_to_id():
    assert map_row(_detail(GateType="1")).gate_type_id == 1
    assert map_row(_detail(GateType="2")).gate_type_id == 2


def test_blank_or_none_gate_type_is_none():
    assert map_row(_detail(GateType=None)).gate_type_id is None
    assert map_row(_detail(GateType="   ")).gate_type_id is None


def test_names_are_trimmed():
    m = map_row(_detail(TruckerName="  All Points Transport  ", EquipCode=" 40STR "))
    assert m.trucker_name == "All Points Transport"
    assert m.equip_code == "40STR"


def test_blank_and_none_names_become_none():
    m = map_row(_detail(TruckerName=None, OceanCarrierName="   ", LocationName=None))
    assert m.trucker_name is None
    assert m.ocean_carrier_name is None
    assert m.location_name is None


def test_null_measures_pass_through_as_none():
    m = map_row(_detail(EquipLength=None, LengthMatchId=None, Units=None, Transactions=None))
    assert m.equip_length is None
    assert m.length_match_id is None
    assert m.units is None
    assert m.transactions is None