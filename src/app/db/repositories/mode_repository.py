"""Repository for Mode_tbl (lookup)."""
from app.db.models.mode import Mode


class ModeRepository:
    def __init__(self, session):
        self.session = session

    def name_to_id(self) -> dict[str, int]:
        return {m.ModeName: m.ModeId for m in self.session.query(Mode).all()}