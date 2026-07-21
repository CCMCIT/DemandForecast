"""Unit test (no DB): the OnTerm writer resolves each name under its FieldType, puts the
id in the matching column, and upserts by identity -- updating the payload of an existing
row (same object, same id) or inserting a new one. A fake resolver stands in for the DB
proc and a fake repository stands in for the DB; no database is touched."""
from datetime import date

import pytest

from app.db.models.on_term_detail import OnTermDetail
from app.lookups import FieldType
from app.processing.on_terminal.dto import MappedOnTerm
from app.processing.on_terminal.writer import (
    FieldTypeValueResolver,
    OnTermWriter,
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
    """Stands in for OnTermDetailRepository: serves preset existing rows for get_by_dates
    and captures inserts from add_all."""

    def __init__(self, existing: list[OnTermDetail] | None = None):
        self.existing = existing or []
        self.added: list[OnTermDetail] = []

    def get_by_dates(self, dates):
        return [r for r in self.existing if r.Date in dates]

    def add_all(self, rows):
        self.added.extend(rows)


def _mapped(**overrides) -> MappedOnTerm:
    base = dict(
        file_id=7, date=date(2026, 1, 14),
        equip_code="40STR", location_name="GPA - Garden City 3.0",
        units=3,
    )
    base.update(overrides)
    return MappedOnTerm(**base)


RESOLVED_IDS = {
    (int(FieldType.EQUIPMENT_TYPE), "40STR"): 202,
    (int(FieldType.LOCATION), "GPA - Garden City 3.0"): 404,
    (int(FieldType.LOCATION), "GPA - Ocean Terminal"): 405,
}


def _write(mapped, existing=None, ids=RESOLVED_IDS):
    repo = FakeDetailsRepo(existing)
    writer = OnTermWriter(session=None, resolver=FakeResolver(ids), details=repo)
    writer.write_details(mapped)
    return repo


def _existing_row(**overrides) -> OnTermDetail:
    """A target row already in the DB, with the SAME identity as the default _mapped()."""
    base = dict(
        OnTermDetailId=555, LoadId=1, Date=date(2026, 1, 14),
        FieldTypeValueEquipTypeId=202, FieldTypeValueLocationId=404,
        Units=99,
    )
    base.update(overrides)
    return OnTermDetail(**base)


# --- insert path (no existing match) ---

def test_new_identity_is_inserted():
    repo = _write([_mapped()])
    assert len(repo.added) == 1
    row = repo.added[0]
    assert row.FieldTypeValueEquipTypeId == 202
    assert row.FieldTypeValueLocationId == 404


def test_inserted_row_copies_all_columns():
    row = _write([_mapped()]).added[0]
    assert (row.LoadId, row.Date) == (7, date(2026, 1, 14))
    assert row.Units == 3


def test_null_name_leaves_its_column_null():
    ids = {**RESOLVED_IDS}
    ids.pop((int(FieldType.EQUIPMENT_TYPE), "40STR"))
    row = _write([_mapped(equip_code=None)], ids=ids).added[0]
    assert row.FieldTypeValueEquipTypeId is None
    assert row.FieldTypeValueLocationId == 404


# --- update path (existing identity) ---

def test_existing_identity_updates_in_place_not_inserted():
    existing = _existing_row()
    repo = _write([_mapped(file_id=7, units=3)], existing=[existing])
    assert repo.added == []                  # nothing inserted
    assert existing.OnTermDetailId == 555    # same row, id untouched
    assert existing.LoadId == 7              # payload updated
    assert existing.Units == 3


def test_update_does_not_touch_identity_columns():
    existing = _existing_row()
    _write([_mapped()], existing=[existing])
    # identity columns stay exactly as they were
    assert existing.FieldTypeValueEquipTypeId == 202
    assert existing.FieldTypeValueLocationId == 404
    assert existing.Date == date(2026, 1, 14)


def test_row_differing_only_by_date_is_a_new_row():
    existing = _existing_row()  # Date 2026-01-14
    repo = _write([_mapped(date=date(2026, 1, 15))], existing=[existing])
    assert len(repo.added) == 1              # different date -> insert
    assert existing.LoadId == 1              # the Jan-14 row untouched


# --- within-batch duplicates ---

def test_duplicate_identity_in_one_batch_collapses_last_wins():
    repo = _write([_mapped(units=3), _mapped(units=9)])
    assert len(repo.added) == 1              # collapsed to one
    assert repo.added[0].Units == 9          # last wins


def test_distinct_identities_each_produce_a_row():
    repo = _write([_mapped(), _mapped(location_name="GPA - Ocean Terminal")])
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