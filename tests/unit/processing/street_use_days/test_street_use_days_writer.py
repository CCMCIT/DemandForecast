"""Unit test (no DB): the StreetUseDays writer resolves each name under its FieldType, puts
the id in the matching column, and upserts by identity -- updating the payload of an existing
row (same object, same id) or inserting a new one. A fake resolver stands in for the DB proc
and a fake repository stands in for the DB; no database is touched."""
from datetime import datetime

import pytest

from app.db.models.street_use_days_detail import StreetUseDaysDetail
from app.lookups import FieldType
from app.processing.street_use_days.dto import MappedStreetUseDays
from app.processing.street_use_days.writer import (
    FieldTypeValueResolver,
    StreetUseDaysWriter,
)

pytestmark = pytest.mark.unit

OUT_GATE = datetime(2026, 1, 14, 8, 0)
IN_GATE = datetime(2026, 1, 20, 17, 30)


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
    """Stands in for StreetUseDaysDetailRepository: serves preset existing rows for
    get_by_out_gate_dates and captures inserts from add_all."""

    def __init__(self, existing: list[StreetUseDaysDetail] | None = None):
        self.existing = existing or []
        self.added: list[StreetUseDaysDetail] = []

    def get_by_out_gate_dates(self, out_gate_dates):
        return [r for r in self.existing if r.OutGateDate in out_gate_dates]

    def add_all(self, rows):
        self.added.extend(rows)


def _mapped(**overrides) -> MappedStreetUseDays:
    base = dict(
        file_id=7,
        out_gate_date=OUT_GATE,
        in_gate_date=IN_GATE,
        og_location_name="GPA - Garden City 3.0",
        ig_location_name="GPA - Ocean Terminal",
        equip_code="40STR",
        ultimate_user="MAERSK",
        count_of_records=3,
    )
    base.update(overrides)
    return MappedStreetUseDays(**base)


RESOLVED_IDS = {
    (int(FieldType.LOCATION), "GPA - Garden City 3.0"): 404,
    (int(FieldType.LOCATION), "GPA - Ocean Terminal"): 405,
    (int(FieldType.EQUIPMENT_TYPE), "40STR"): 202,
    (int(FieldType.OCEAN_CARRIER), "MAERSK"): 303,
}


def _write(mapped, existing=None, ids=RESOLVED_IDS):
    repo = FakeDetailsRepo(existing)
    writer = StreetUseDaysWriter(session=None, resolver=FakeResolver(ids), details=repo)
    writer.write_details(mapped)
    return repo


def _existing_row(**overrides) -> StreetUseDaysDetail:
    """A target row already in the DB, with the SAME identity as the default _mapped()."""
    base = dict(
        StreetUseDaysDetailId=555, LoadId=1,
        OutGateDate=OUT_GATE, FieldTypeValueOGLocationId=404,
        InGateDate=IN_GATE, FieldTypeValueIGLocationId=405,
        FieldTypeValueEquipTypeId=202, FieldTypeValueOceanCarrierId=303,
        CountOfRecords=99,
    )
    base.update(overrides)
    return StreetUseDaysDetail(**base)


# --- insert path (no existing match) ---

def test_new_identity_is_inserted():
    repo = _write([_mapped()])
    assert len(repo.added) == 1
    row = repo.added[0]
    assert row.FieldTypeValueOGLocationId == 404
    assert row.FieldTypeValueIGLocationId == 405
    assert row.FieldTypeValueEquipTypeId == 202
    assert row.FieldTypeValueOceanCarrierId == 303


def test_inserted_row_copies_all_columns():
    row = _write([_mapped()]).added[0]
    assert row.LoadId == 7
    assert row.OutGateDate == OUT_GATE
    assert row.InGateDate == IN_GATE
    assert row.CountOfRecords == 3


def test_null_name_leaves_its_column_null():
    ids = {**RESOLVED_IDS}
    ids.pop((int(FieldType.OCEAN_CARRIER), "MAERSK"))
    row = _write([_mapped(ultimate_user=None)], ids=ids).added[0]
    assert row.FieldTypeValueOceanCarrierId is None
    assert row.FieldTypeValueEquipTypeId == 202


# --- update path (existing identity) ---

def test_existing_identity_updates_in_place_not_inserted():
    existing = _existing_row()
    repo = _write([_mapped(file_id=7, count_of_records=3)], existing=[existing])
    assert repo.added == []                        # nothing inserted
    assert existing.StreetUseDaysDetailId == 555   # same row, id untouched
    assert existing.LoadId == 7                    # payload updated
    assert existing.CountOfRecords == 3


def test_update_does_not_touch_identity_columns():
    existing = _existing_row()
    _write([_mapped()], existing=[existing])
    assert existing.OutGateDate == OUT_GATE
    assert existing.FieldTypeValueOGLocationId == 404
    assert existing.InGateDate == IN_GATE
    assert existing.FieldTypeValueIGLocationId == 405
    assert existing.FieldTypeValueEquipTypeId == 202
    assert existing.FieldTypeValueOceanCarrierId == 303


def test_row_differing_only_by_out_gate_date_is_a_new_row():
    existing = _existing_row()  # OutGateDate 2026-01-14 08:00
    repo = _write([_mapped(out_gate_date=datetime(2026, 1, 15, 8, 0))], existing=[existing])
    assert len(repo.added) == 1                    # different OutGateDate -> insert
    assert existing.LoadId == 1                    # original row untouched


def test_row_differing_only_by_in_gate_date_is_a_new_row():
    # Same OutGateDate (so the fetch returns the existing row) but a different InGateDate,
    # which is part of the identity -> the in-memory compare must treat it as a new row.
    existing = _existing_row()
    repo = _write([_mapped(in_gate_date=datetime(2026, 1, 21, 9, 0))], existing=[existing])
    assert len(repo.added) == 1
    assert existing.LoadId == 1                    # original row untouched


def test_null_in_gate_date_matches_null_in_gate_date():
    # InGateDate is nullable; None must match None in the identity (update, not insert).
    existing = _existing_row(InGateDate=None)
    repo = _write([_mapped(in_gate_date=None, count_of_records=5)], existing=[existing])
    assert repo.added == []
    assert existing.CountOfRecords == 5


# --- within-batch duplicates ---

def test_duplicate_identity_in_one_batch_collapses_last_wins():
    repo = _write([_mapped(count_of_records=3), _mapped(count_of_records=9)])
    assert len(repo.added) == 1                    # collapsed to one
    assert repo.added[0].CountOfRecords == 9       # last wins


def test_distinct_identities_each_produce_a_row():
    repo = _write([_mapped(), _mapped(ig_location_name="GPA - Garden City 3.0")])
    assert len(repo.added) == 2


# --- resolver caching ---

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
        resolver.resolve(int(FieldType.LOCATION), "GPA - Garden City 3.0")
    assert session.execute_count == 1


def test_resolver_returns_none_without_calling_the_proc_for_a_null_value():
    session = RecordingSession()
    resolver = FieldTypeValueResolver(session)
    assert resolver.resolve(int(FieldType.LOCATION), None) is None
    assert session.execute_count == 0
