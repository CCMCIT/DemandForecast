"""Repository for CmsOutOfServiceUnitsDetail (CMS raw out-of-service rows)."""
from app.db.models.cms_out_of_service_units_detail import CmsOutOfServiceUnitsDetail


class CmsOutOfServiceUnitsDetailRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[CmsOutOfServiceUnitsDetail]) -> None:
        self.session.add_all(details)

    def get_by_file_id(self, file_id: int) -> list[CmsOutOfServiceUnitsDetail]:
        return (
            self.session.query(CmsOutOfServiceUnitsDetail)
            .filter(CmsOutOfServiceUnitsDetail.LoadId == file_id)
            .all()
        )
