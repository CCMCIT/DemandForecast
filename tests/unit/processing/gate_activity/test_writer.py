"""Unit test (no DB): the GateActivity writer resolves each name under its FieldType
and puts the id in the matching column; NULL names stay NULL. A fake resolver stands in
for the DB proc, and a fake session captures the rows -- no database is touched."""
from datetime import date

import pytest

from app.lookups import FieldType
from app.processing.gate_activity.dto import MappedGateActivity
from app.processing.gate_activity.writer import (
    FieldTypeValueResolver,
    GateActivityWriter,
)

pytestmark = pytest.mark.unit


class FakeResolver:
    """Returns a deterministic id per (FieldType, value) and records every call, so a
    test can assert both the id-to-column mapping and how often the proc would run."""

    def __init__(self, ids: dict[tuple[int, str], int]):
        self.ids = ids
        self.calls: list[tuple[int, str]] = []

    def resolve(self, field_type_id: int, value):
        if value is None:
            return None
        self.calls.append((field_type_id, value))
        return self.ids[(field_type_id, value)]


class FakeSession:
    def __init__(self):
        self.added: list = []

    def add_all(self, rows):
        self.added.extend(rows)


def _mapped(**overrides) -> MappedGateActivity:
    base = dict(
        file_id=7, date=date(2026, 1, 14),
        trucker_name="All Points Transport", equip_code="40STR",
        ocean_carrier_name="Maersk A/S", location_name="GPA - Garden City 3.0",
        equip_length=40, length_match_id=1, gate_type_id=1,
        bare_chassis_flag=False, container_loaded_flag=True,
        units=3, transactions=2,
    )
    base.update(overrides)
    return MappedGateActivity(**base)


RESOLVED_IDS = {
    (int(FieldType.TRUCKER), "All Points Transport"): 101,
    (int(FieldType.EQUIPMENT_TYPE), "40STR"): 202,
    (int(FieldType.OCEAN_CARRIER), "Maersk A/S"): 303,
    (int(FieldType.LOCATION), "GPA - Garden City 3.0"): 404,
}


def _write(mapped, ids=RESOLVED_IDS):
    session, resolver = FakeSession(), FakeResolver(ids)
    GateActivityWriter(session, resolver=resolver).write_details(mapped)
    return session, resolver


def test_each_name_resolves_into_its_column():
    session, _ = _write([_mapped()])
    row = session.added[0]
    assert row.FieldTypeValueTruckerId == 101
    assert row.FieldTypeValueEquipTypeId == 202
    assert row.FieldTypeValueOceanCarrierId == 303
    assert row.FieldTypeValueLocationId == 404


def test_plain_columns_are_copied():
    session, _ = _write([_mapped()])
    row = session.added[0]
    assert (row.FileId, row.Date) == (7, date(2026, 1, 14))
    assert (row.EquipLength, row.LengthMatchId, row.GateTypeId) == (40, 1, 1)
    assert (row.BareChassisFlag, row.ContainerLoadedFlag) == (False, True)
    assert (row.Units, row.Transactions) == (3, 2)


def test_null_name_leaves_its_column_null():
    ids = {**RESOLVED_IDS}
    ids.pop((int(FieldType.TRUCKER), "All Points Transport"))
    session, _ = _write([_mapped(trucker_name=None)], ids=ids)
    assert session.added[0].FieldTypeValueTruckerId is None
    # the other three still resolve
    assert session.added[0].FieldTypeValueOceanCarrierId == 303


def test_one_row_per_mapped_row():
    session, _ = _write([_mapped(), _mapped(), _mapped()])
    assert len(session.added) == 3


class RecordingSession:
    """Counts proc executions and returns a fixed id, standing in for the DB."""

    def __init__(self):
        self.execute_count = 0

    def execute(self, *_args, **_kwargs):
        self.execute_count += 1
        return _ScalarResult(999)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


def test_resolver_calls_the_proc_once_per_distinct_value():
    session = RecordingSession()
    resolver = FieldTypeValueResolver(session)
    for _ in range(5):
        resolver.resolve(int(FieldType.TRUCKER), "All Points Transport")
    assert session.execute_count == 1  # cached after the first call


def test_resolver_returns_none_without_calling_the_proc_for_a_null_value():
    session = RecordingSession()
    resolver = FieldTypeValueResolver(session)
    assert resolver.resolve(int(FieldType.TRUCKER), None) is None
    assert session.execute_count == 0  # no proc call for a NULL name