"""Purpose: upsert MappedOutOfService rows into OutOfServiceUnitsDetail_tbl.

Each of the two descriptive names (Equipment / Location) is resolved to a FieldTypeValue id
under its FieldType, and the id lands in the matching column. Resolution goes through the DB
proc GateActivityFieldTypeValue_upsert (a generic find-or-create; the gate-activity name is
historical), so a value new to the dimension is created, not rejected -- the sets are open.

A row's IDENTITY is its 3 columns (Date + the two dimension columns); Units and LoadId are
the mutable payload. On write, a row whose identity already exists is UPDATED in place --
same OutOfServiceUnitsDetailId, temporal archives the prior version -- and only its
Units/LoadId change. A new identity is inserted. Within one batch a repeated identity is
collapsed last-wins (the DB unique constraint forbids two live rows with the same identity
anyway).

The resolver caches per run: each distinct (FieldType, value) hits the proc once. The writer
does no commit -- the runner owns the transaction. A NULL/blank name resolves to None: no
proc call, the column left NULL (and None matches None in the identity).
"""
from sqlalchemy import text

from app.db.models.out_of_service_units_detail import OutOfServiceUnitsDetail
from app.db.repositories.out_of_service_units_detail_repository import (
    OutOfServiceUnitsDetailRepository,
)
from app.lookups import FieldType
from app.processing.out_of_service.dto import MappedOutOfService

# (MappedOutOfService attr holding the name, FieldType to resolve under, target column)
OUT_OF_SERVICE_FIELD_MAP = [
    ("equip_code",    FieldType.EQUIPMENT_TYPE, "FieldTypeValueEquipTypeId"),
    ("location_name", FieldType.LOCATION,       "FieldTypeValueLocationId"),
]

# The columns that identify a row (Date + the two dimensions). Two rows with the same values
# here are the same out-of-service measurement; everything else is mutable payload.
IDENTITY_COLUMNS = [
    "Date",
    "FieldTypeValueEquipTypeId",
    "FieldTypeValueLocationId",
]

# The columns updated when an identity already exists.
PAYLOAD_COLUMNS = ["LoadId", "Units"]


class FieldTypeValueResolver:
    """Resolve a (FieldType, value) to its FieldTypeValueId via the upsert proc,
    caching each distinct pair for the life of the resolver (one per run).

    Duplicated from the gate-activity writer on purpose: out_of_service is its own domain
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
    """The 3-column identity of an OutOfServiceUnitsDetail (existing row or freshly built)."""
    return tuple(getattr(row, column) for column in IDENTITY_COLUMNS)


class OutOfServiceWriter:
    def __init__(self, session, resolver: FieldTypeValueResolver | None = None,
                 details: OutOfServiceUnitsDetailRepository | None = None):
        self.details = details or OutOfServiceUnitsDetailRepository(session)
        self.resolver = resolver or FieldTypeValueResolver(session)

    def write_details(self, mapped: list[MappedOutOfService]) -> None:
        """Upsert each row by its identity: update the payload of an existing row,
        or insert a new one."""
        # Build the target rows and collapse within-batch duplicates (last-wins), so
        # we never try to insert two rows with the same identity.
        incoming: dict[tuple, OutOfServiceUnitsDetail] = {}
        for m in mapped:
            row = self._to_detail(m)
            incoming[_identity(row)] = row

        existing = {
            _identity(row): row
            for row in self.details.get_by_dates({d.Date for d in incoming.values()})
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

    def _to_detail(self, m: MappedOutOfService) -> OutOfServiceUnitsDetail:
        resolved_ids = {
            column: self.resolver.resolve(int(field_type), getattr(m, attr))
            for attr, field_type, column in OUT_OF_SERVICE_FIELD_MAP
        }
        return OutOfServiceUnitsDetail(
            LoadId=m.file_id,
            Date=m.date,
            Units=m.units,
            **resolved_ids,
        )
