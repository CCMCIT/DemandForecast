"""Purpose: upsert MappedGateActivity rows into GateActivityDetail_tbl.

Each of the four descriptive names (Trucker / Equipment / Ocean Carrier / Location) is
resolved to a FieldTypeValue id under its FieldType, and the id lands in the matching
column. Resolution goes through the DB proc GateActivityFieldTypeValue_upsert (find-or-
create), so a value new to the dimension is created, not rejected -- the sets are open.

A row's IDENTITY is its 10 columns (Date + the nine dimension columns); Units,
Transactions and LoadId are the mutable payload. On write, a row whose identity already
exists is UPDATED in place -- same GateActivityDetailId, temporal archives the prior
version -- and only its payload changes. A new identity is inserted. Within one batch a
repeated identity is collapsed last-wins (the DB unique constraint forbids two live rows
with the same identity anyway).

The resolver caches per run: each distinct (FieldType, value) hits the proc once. The
writer does no commit -- the runner owns the transaction. A NULL/blank name resolves to
None: no proc call, the column left NULL (and None matches None in the identity).
"""
from sqlalchemy import text

from app.db.models.gate_activity_detail import GateActivityDetail
from app.db.repositories.gate_activity_detail_repository import GateActivityDetailRepository
from app.lookups import FieldType
from app.processing.gate_activity.dto import MappedGateActivity

# (MappedGateActivity attr holding the name, FieldType to resolve under, target column)
GATE_ACTIVITY_FIELD_MAP = [
    ("trucker_name",       FieldType.TRUCKER,        "FieldTypeValueTruckerId"),
    ("equip_code",         FieldType.EQUIPMENT_TYPE, "FieldTypeValueEquipTypeId"),
    ("ocean_carrier_name", FieldType.OCEAN_CARRIER,  "FieldTypeValueOceanCarrierId"),
    ("location_name",      FieldType.LOCATION,       "FieldTypeValueLocationId"),
]

# The columns that identify a row (Date + the nine dimensions). Two rows with the same
# values here are the same gate movement; everything else is mutable payload.
IDENTITY_COLUMNS = [
    "Date",
    "FieldTypeValueTruckerId",
    "FieldTypeValueEquipTypeId",
    "EquipLength",
    "LengthMatchId",
    "FieldTypeValueOceanCarrierId",
    "GateTypeId",
    "BareChassisFlag",
    "ContainerLoadedFlag",
    "FieldTypeValueLocationId",
]

# The columns updated when an identity already exists.
PAYLOAD_COLUMNS = ["LoadId", "Units", "Transactions"]


class FieldTypeValueResolver:
    """Resolve a (FieldType, value) to its FieldTypeValueId via the upsert proc,
    caching each distinct pair for the life of the resolver (one per run)."""

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
    """The 10-column identity of a GateActivityDetail (existing row or freshly built)."""
    return tuple(getattr(row, column) for column in IDENTITY_COLUMNS)


class GateActivityWriter:
    def __init__(self, session, resolver: FieldTypeValueResolver | None = None,
                 details: GateActivityDetailRepository | None = None):
        self.details = details or GateActivityDetailRepository(session)
        self.resolver = resolver or FieldTypeValueResolver(session)

    def write_details(self, mapped: list[MappedGateActivity]) -> None:
        """Upsert each row by its identity: update the payload of an existing row,
        or insert a new one."""
        # Build the target rows and collapse within-batch duplicates (last-wins), so
        # we never try to insert two rows with the same identity.
        incoming: dict[tuple, GateActivityDetail] = {}
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

    def _to_detail(self, m: MappedGateActivity) -> GateActivityDetail:
        resolved_ids = {
            column: self.resolver.resolve(int(field_type), getattr(m, attr))
            for attr, field_type, column in GATE_ACTIVITY_FIELD_MAP
        }
        return GateActivityDetail(
            LoadId=m.file_id,
            Date=m.date,
            EquipLength=m.equip_length,
            LengthMatchId=m.length_match_id,
            GateTypeId=m.gate_type_id,
            BareChassisFlag=m.bare_chassis_flag,
            ContainerLoadedFlag=m.container_loaded_flag,
            Units=m.units,
            Transactions=m.transactions,
            **resolved_ids,
        )