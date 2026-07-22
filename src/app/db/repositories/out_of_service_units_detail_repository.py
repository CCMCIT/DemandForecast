"""Repository for OutOfServiceUnitsDetail_tbl (processed out-of-service target)."""
from datetime import date

from app.db.models.out_of_service_units_detail import OutOfServiceUnitsDetail


class OutOfServiceUnitsDetailRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[OutOfServiceUnitsDetail]) -> None:
        self.session.add_all(details)

    def get_by_dates(self, dates: set[date]) -> list[OutOfServiceUnitsDetail]:
        """Existing target rows whose Date is in `dates`. Loaded once so the writer
        can match incoming rows against them by identity in memory. Scoped to the
        batch's dates (Date is part of the identity), so it never loads the whole
        table."""
        if not dates:
            return []
        return (
            self.session.query(OutOfServiceUnitsDetail)
            .filter(OutOfServiceUnitsDetail.Date.in_(dates))
            .all()
        )
