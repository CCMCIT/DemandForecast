"""Repository for StreetUseDaysDetail_tbl (processed street-use-days target)."""
from datetime import datetime

from app.db.models.street_use_days_detail import StreetUseDaysDetail


class StreetUseDaysDetailRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[StreetUseDaysDetail]) -> None:
        self.session.add_all(details)

    def get_by_out_gate_dates(
        self, out_gate_dates: set[datetime]
    ) -> list[StreetUseDaysDetail]:
        """Existing target rows whose OutGateDate is in `out_gate_dates`. Loaded once so
        the writer can match incoming rows against them by identity (all 6 columns) in
        memory. Filtering on OutGateDate alone can't miss a match -- it is part of the
        identity, so a true match always shares it -- and keeps the fetch bounded to the
        batch's dates instead of the whole table (OutGateDate is NOT NULL)."""
        if not out_gate_dates:
            return []
        return (
            self.session.query(StreetUseDaysDetail)
            .filter(StreetUseDaysDetail.OutGateDate.in_(out_gate_dates))
            .all()
        )
