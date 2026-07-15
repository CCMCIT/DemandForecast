"""Repository for GateActivityDetail_tbl (processed gate-activity target)."""
from app.db.models.gate_activity_detail import GateActivityDetail


class GateActivityDetailRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[GateActivityDetail]) -> None:
        self.session.add_all(details)

    def delete_by_file_id(self, file_id: int) -> None:
        """Delete a file's target rows. Reprocessing a file is delete-by-FileId then
        re-insert (the table has no natural key to replace on, unlike Voyage)."""
        self.session.query(GateActivityDetail).filter(
            GateActivityDetail.FileId == file_id
        ).delete(synchronize_session=False)