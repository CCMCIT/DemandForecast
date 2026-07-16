"""Repository for GateActivityDetail_tbl (processed gate-activity target)."""
from datetime import date

from app.db.models.gate_activity_detail import GateActivityDetail


class GateActivityDetailRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[GateActivityDetail]) -> None:
        self.session.add_all(details)

    def get_by_dates(self, dates: set[date]) -> list[GateActivityDetail]:
        """Existing target rows whose Date is in `dates`. Loaded once so the writer
        can match incoming rows against them by identity in memory. Scoped to the
        batch's dates (Date is part of the identity), so it never loads the whole
        table."""
        if not dates:
            return []
        return (
            self.session.query(GateActivityDetail)
            .filter(GateActivityDetail.Date.in_(dates))
            .all()
        )