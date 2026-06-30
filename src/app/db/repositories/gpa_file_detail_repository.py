"""Repository for GpaFileDetail_tbl (GPA raw rows)."""
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