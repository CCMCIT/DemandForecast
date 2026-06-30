"""Repository for Direction_tbl (lookup)."""
from app.db.models.direction import Direction


class DirectionRepository:
    def __init__(self, session):
        self.session = session

    def name_to_id(self) -> dict[str, int]:
        return {d.DirectionName: d.DirectionId for d in self.session.query(Direction).all()}