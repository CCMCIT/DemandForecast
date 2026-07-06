"""Repository for GpaFileDetail_tbl (GPA raw rows)."""
from datetime import date, datetime

from app.db.models.gpa_file_detail import GpaFileDetail


class GpaFileDetailRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[GpaFileDetail]) -> None:
        self.session.add_all(details)

    def get_by_file_id(self, file_id: int) -> list[GpaFileDetail]:
        return (
            self.session.query(GpaFileDetail)
            .filter(GpaFileDetail.FileId == file_id)
            .all()
        )

    def get_reported_date(self, file_id: int, voyage: str) -> date | None:
        """The parsed REPORTED date for a voyage's row in a given file, or None.
        REPORTED is stored as an MMDDYYYY string (e.g. '07032025')."""
        row = (
            self.session.query(GpaFileDetail.REPORTED)
            .filter(GpaFileDetail.FileId == file_id, GpaFileDetail.VOYAGE == voyage)
            .first()
        )
        if row is None or not row.REPORTED:
            return None
        try:
            return datetime.strptime(row.REPORTED.strip(), "%m%d%Y").date()
        except ValueError:
            return None