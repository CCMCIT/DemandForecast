"""Repository for VoyageDetails_tbl. Shared target."""
from app.db.models.voyage_details import VoyageDetails


class VoyageDetailsRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[VoyageDetails]) -> None:
        self.session.add_all(details)