"""Repository for CmsGateActivityDetail (CMS raw gate-activity rows)."""
from app.db.models.cms_gate_activity_detail import CmsGateActivityDetail


class CmsGateActivityDetailRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[CmsGateActivityDetail]) -> None:
        self.session.add_all(details)

    def get_by_file_id(self, file_id: int) -> list[CmsGateActivityDetail]:
        return (
            self.session.query(CmsGateActivityDetail)
            .filter(CmsGateActivityDetail.FileId == file_id)
            .all()
        )