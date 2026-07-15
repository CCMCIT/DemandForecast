"""Repository for GateType (lookup)."""
from app.db.models.gate_type import GateType


class GateTypeRepository:
    def __init__(self, session):
        self.session = session

    def id_set(self) -> set[int]:
        """The valid GateTypeIds, loaded once per run so the mapper can reject an
        unknown gate type without a per-row DB hit."""
        return {row.GateTypeId for row in self.session.query(GateType.GateTypeId).all()}