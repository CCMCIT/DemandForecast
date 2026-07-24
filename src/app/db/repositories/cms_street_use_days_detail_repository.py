"""Repository for CmsStreetUseDaysDetail (CMS raw street-use-days rows)."""
from app.db.models.cms_street_use_days_detail import CmsStreetUseDaysDetail


class CmsStreetUseDaysDetailRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[CmsStreetUseDaysDetail]) -> None:
        self.session.add_all(details)

    def get_by_file_id(self, file_id: int) -> list[CmsStreetUseDaysDetail]:
        return (
            self.session.query(CmsStreetUseDaysDetail)
            .filter(CmsStreetUseDaysDetail.LoadId == file_id)
            .all()
        )
