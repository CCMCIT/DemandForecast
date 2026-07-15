"""Purpose: persist MappedGateActivity rows into GateActivityDetail_tbl.

Each of the four descriptive names (Trucker / Equipment / Ocean Carrier / Location) is
resolved to a FieldTypeValue id under its FieldType, and the id lands in the matching
column. Resolution goes through the DB proc GateActivityFieldTypeValue_upsert (find-or-
create), so a value new to the dimension is created, not rejected -- the sets are open.

The resolver caches per run: each distinct (FieldType, value) hits the proc once, so a
file of many rows over few truckers/carriers costs few proc calls, not one per row. The
writer does no commit -- the runner owns the transaction (same contract as the voyage
writer). A NULL/blank name resolves to None: no proc call, the column is left NULL.
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


class GateActivityWriter:
    def __init__(self, session, resolver: FieldTypeValueResolver | None = None):
        self.details = GateActivityDetailRepository(session)
        self.resolver = resolver or FieldTypeValueResolver(session)

    def write_details(self, mapped: list[MappedGateActivity]) -> None:
        """Resolve each row's names and insert the GateActivityDetail rows (1:1)."""
        self.details.add_all([self._to_detail(m) for m in mapped])

    def _to_detail(self, m: MappedGateActivity) -> GateActivityDetail:
        resolved_ids = {
            column: self.resolver.resolve(int(field_type), getattr(m, attr))
            for attr, field_type, column in GATE_ACTIVITY_FIELD_MAP
        }
        return GateActivityDetail(
            FileId=m.file_id,
            Date=m.date,
            EquipLength=m.equip_length,
            LengthMatch=m.length_match,
            GateTypeId=m.gate_type_id,
            BareChassisFlag=m.bare_chassis_flag,
            ContainerLoadedFlag=m.container_loaded_flag,
            Units=m.units,
            Transactions=m.transactions,
            GateActivityStatusId=None,  # no source yet; left NULL by design
            **resolved_ids,
        )