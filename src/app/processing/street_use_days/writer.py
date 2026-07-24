"""Purpose: upsert MappedStreetUseDays rows into StreetUseDaysDetail_tbl.

Each of the four descriptive names (out/in gate location, equipment, ultimate user) is
resolved to a FieldTypeValue id under its FieldType, and the id lands in the matching column.
Resolution goes through the DB proc GateActivityFieldTypeValue_upsert (a generic find-or-create;
the gate-activity name is historical), so a value new to the dimension is created, not rejected
-- the sets are open.

A row's IDENTITY is its 6 descriptive columns (both gate dates + the four FieldTypeValue ids);
LoadId and CountOfRecords are the mutable payload. On write, a row whose identity already exists
is UPDATED in place -- same StreetUseDaysDetailId, temporal archives the prior version -- and only
its LoadId/CountOfRecords change. A new identity is inserted. Within one batch a repeated identity
is collapsed last-wins (the DB unique constraint UQ_StreetUseDaysDetail_Identity forbids two live
rows with the same identity anyway).

The resolver caches per run: each distinct (FieldType, value) hits the proc once. The writer does
no commit -- the runner owns the transaction. A NULL/blank name resolves to None: no proc call, the
column left NULL (and None matches None in the identity). InGateDate may be None likewise; OutGateDate
is always present (NOT NULL) and scopes the existing-row fetch.
"""
from sqlalchemy import text

from app.db.models.street_use_days_detail import StreetUseDaysDetail
from app.db.repositories.street_use_days_detail_repository import (
    StreetUseDaysDetailRepository,
)
from app.lookups import FieldType
from app.processing.street_use_days.dto import MappedStreetUseDays

# (MappedStreetUseDays attr holding the name, FieldType to resolve under, target column)
STREET_USE_DAYS_FIELD_MAP = [
    ("og_location_name", FieldType.LOCATION,       "FieldTypeValueOGLocationId"),
    ("ig_location_name", FieldType.LOCATION,       "FieldTypeValueIGLocationId"),
    ("equip_code",       FieldType.EQUIPMENT_TYPE, "FieldTypeValueEquipTypeId"),
    ("ultimate_user",    FieldType.OCEAN_CARRIER,  "FieldTypeValueOceanCarrierId"),
]

# The columns that identify a row (both gate dates + the four dimensions). Two rows with the
# same values here are the same street-use-days measurement; everything else is mutable payload.
IDENTITY_COLUMNS = [
    "OutGateDate",
    "FieldTypeValueOGLocationId",
    "InGateDate",
    "FieldTypeValueIGLocationId",
    "FieldTypeValueEquipTypeId",
    "FieldTypeValueOceanCarrierId",
]

# The columns updated when an identity already exists.
PAYLOAD_COLUMNS = ["LoadId", "CountOfRecords"]


class FieldTypeValueResolver:
    """Resolve a (FieldType, value) to its FieldTypeValueId via the upsert proc,
    caching each distinct pair for the life of the resolver (one per run).

    Duplicated from the gate-activity writer on purpose: street_use_days is its own domain
    and must not import another domain's internals (see CLAUDE.md modularity rules)."""

    def __init__(self, session):
        self.session = session
        self._cache: dict[tuple[int, str], int] = {}

    def resolve(self, field_type_id: int, value: str | None) -> int | None:
        if value is None:
            return None
        key = (field_type_id, value)
        if key not in self._cache:
            self._cache[key] = self._upsert(field_type_id, value)
        return self._cache[key]

    def _upsert(self, field_type_id: int, value: str) -> int:
        return self.session.execute(
            text(
                "DECLARE @id int; "
                "EXEC DemandForecast.GateActivityFieldTypeValue_upsert "
                ":field_type_id, :field_value, @id OUTPUT; "
                "SELECT @id;"
            ),
            {"field_type_id": field_type_id, "field_value": value},
        ).scalar()


def _identity(row) -> tuple:
    """The 6-column identity of a StreetUseDaysDetail (existing row or freshly built)."""
    return tuple(getattr(row, column) for column in IDENTITY_COLUMNS)


class StreetUseDaysWriter:
    def __init__(self, session, resolver: FieldTypeValueResolver | None = None,
                 details: StreetUseDaysDetailRepository | None = None):
        self.details = details or StreetUseDaysDetailRepository(session)
        self.resolver = resolver or FieldTypeValueResolver(session)

    def write_details(self, mapped: list[MappedStreetUseDays]) -> None:
        """Upsert each row by its identity: update the payload of an existing row,
        or insert a new one."""
        # Build the target rows and collapse within-batch duplicates (last-wins), so
        # we never try to insert two rows with the same identity.
        incoming: dict[tuple, StreetUseDaysDetail] = {}
        for m in mapped:
            row = self._to_detail(m)
            incoming[_identity(row)] = row

        existing = {
            _identity(row): row
            for row in self.details.get_by_out_gate_dates(
                {d.OutGateDate for d in incoming.values()}
            )
        }

        to_insert = []
        for identity, row in incoming.items():
            current = existing.get(identity)
            if current is None:
                to_insert.append(row)
            else:
                for column in PAYLOAD_COLUMNS:            # update payload in place;
                    setattr(current, column, getattr(row, column))  # identity unchanged
        self.details.add_all(to_insert)

    def _to_detail(self, m: MappedStreetUseDays) -> StreetUseDaysDetail:
        resolved_ids = {
            column: self.resolver.resolve(int(field_type), getattr(m, attr))
            for attr, field_type, column in STREET_USE_DAYS_FIELD_MAP
        }
        return StreetUseDaysDetail(
            LoadId=m.file_id,
            OutGateDate=m.out_gate_date,
            InGateDate=m.in_gate_date,
            CountOfRecords=m.count_of_records,
            **resolved_ids,
        )
