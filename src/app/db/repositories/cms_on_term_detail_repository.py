"""Repository for CmsOnTermDetail (CMS raw on-terminal rows)."""
from app.db.models.cms_on_term_detail import CmsOnTermDetail


class CmsOnTermDetailRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[CmsOnTermDetail]) -> None:
        self.session.add_all(details)

    def get_by_file_id(self, file_id: int) -> list[CmsOnTermDetail]:
        return (
            self.session.query(CmsOnTermDetail)
            .filter(CmsOnTermDetail.LoadId == file_id)
            .all()
        )