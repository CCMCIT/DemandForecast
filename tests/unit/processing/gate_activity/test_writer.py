"""Unit test (no DB): the GateActivity writer resolves each name under its FieldType,
puts the id in the matching column, and upserts by identity -- updating the payload of an
existing row (same object, same id) or inserting a new one. A fake resolver stands in for
the DB proc and a fake repository stands in for the DB; no database is touched."""
from datetime import date

import pytest

from app.db.models.gate_activity_detail import GateActivityDetail
from app.lookups import FieldType
from app.processing.gate_activity.dto import MappedGateActivity
from app.processing.gate_activity.writer import (
    FieldTypeValueResolver,
    GateActivityWriter,
)

pytestmark = pytest.mark.unit


class FakeResolver:
    """Returns a deterministic id per (FieldType, value) and records every call."""

    def __init__(self, ids: dict[tuple[int, str], int]):
        self.ids = ids
        self.calls: list[tuple[int, str]] = []

    def resolve(self, field_type_id: int, value):
        if value is None:
            return None
        self.calls.append((field_type_id, value))
        return self.ids[(field_type_id, value)]


class FakeDetailsRepo:
    """Stands in for GateActivityDetailRepository: serves preset existing rows for
    get_by_dates and captures inserts from add_all."""

    def __init__(self, existing: list[GateActivityDetail] | None = None):
        self.existing = existing or []
        self.added: list[GateActivityDetail] = []

    def get_by_dates(self, dates):
        return [r for r in self.existing if r.Date in dates]

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


def _write(mapped, existing=None, ids=RESOLVED_IDS):
    repo = FakeDetailsRepo(existing)
    writer = GateActivityWriter(session=None, resolver=FakeResolver(ids), details=repo)
    writer.write_details(mapped)
    return repo


def _existing_row(**overrides) -> GateActivityDetail:
    """A target row already in the DB, with the SAME identity as the default _mapped()."""
    base = dict(
        GateActivityDetailId=555, FileId=1, Date=date(2026, 1, 14),
        FieldTypeValueTruckerId=101, FieldTypeValueEquipTypeId=202,
        FieldTypeValueOceanCarrierId=303, FieldTypeValueLocationId=404,
        EquipLength=40, LengthMatchId=1, GateTypeId=1,
        BareChassisFlag=False, ContainerLoadedFlag=True,
        Units=99, Transactions=88,
    )
    base.update(overrides)
    return GateActivityDetail(**base)


# --- insert path (no existing match) ---

def test_new_identity_is_inserted():
    repo = _write([_mapped()])
    assert len(repo.added) == 1
    row = repo.added[0]
    assert row.FieldTypeValueTruckerId == 101
    assert row.FieldTypeValueEquipTypeId == 202
    assert row.FieldTypeValueOceanCarrierId == 303
    assert row.FieldTypeValueLocationId == 404


def test_inserted_row_copies_all_columns():
    row = _write([_mapped()]).added[0]
    assert (row.FileId, row.Date) == (7, date(2026, 1, 14))
    assert (row.EquipLength, row.LengthMatchId, row.GateTypeId) == (40, 1, 1)
    assert (row.BareChassisFlag, row.ContainerLoadedFlag) == (False, True)
    assert (row.Units, row.Transactions) == (3, 2)


def test_null_name_leaves_its_column_null():
    ids = {**RESOLVED_IDS}
    ids.pop((int(FieldType.TRUCKER), "All Points Transport"))
    row = _write([_mapped(trucker_name=None)], ids=ids).added[0]
    assert row.FieldTypeValueTruckerId is None
    assert row.FieldTypeValueOceanCarrierId == 303


# --- update path (existing identity) ---

def test_existing_identity_updates_in_place_not_inserted():
    existing = _existing_row()
    repo = _write([_mapped(file_id=7, units=3, transactions=2)], existing=[existing])
    assert repo.added == []                 # nothing inserted
    assert existing.GateActivityDetailId == 555  # same row, id untouched
    assert existing.FileId == 7             # payload updated
    assert existing.Units == 3
    assert existing.Transactions == 2


def test_update_does_not_touch_identity_columns():
    existing = _existing_row()
    _write([_mapped()], existing=[existing])
    # identity columns stay exactly as they were
    assert existing.FieldTypeValueTruckerId == 101
    assert existing.Date == date(2026, 1, 14)
    assert existing.GateTypeId == 1


def test_row_differing_only_by_date_is_a_new_row():
    existing = _existing_row()  # Date 2026-01-14
    repo = _write([_mapped(date=date(2026, 1, 15))], existing=[existing])
    assert len(repo.added) == 1             # different movement date -> insert
    assert existing.FileId == 1             # the Jan-14 row untouched


# --- within-batch duplicates ---

def test_duplicate_identity_in_one_batch_collapses_last_wins():
    repo = _write([_mapped(units=3, transactions=2), _mapped(units=9, transactions=8)])
    assert len(repo.added) == 1             # collapsed to one
    assert (repo.added[0].Units, repo.added[0].Transactions) == (9, 8)  # last wins


def test_distinct_identities_each_produce_a_row():
    repo = _write([_mapped(), _mapped(gate_type_id=2)])
    assert len(repo.added) == 2


# --- resolver caching (unchanged) ---

class RecordingSession:
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
    assert session.execute_count == 1


def test_resolver_returns_none_without_calling_the_proc_for_a_null_value():
    session = RecordingSession()
    resolver = FieldTypeValueResolver(session)
    assert resolver.resolve(int(FieldType.TRUCKER), None) is None
    assert session.execute_count == 0