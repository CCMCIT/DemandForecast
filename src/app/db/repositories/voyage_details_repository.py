"""Repository for VoyageDetails_tbl. Shared target."""
from app.db.models.voyage_details import VoyageDetails


class VoyageDetailsRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[VoyageDetails]) -> None:
        self.session.add_all(details)

    def delete_by_voyage_id(self, voyage_id: int) -> None:
        """Delete a voyage's detail rows. On a system-versioned table this
        archives them to VoyageDetailsHistory_tbl."""
        self.session.query(VoyageDetails).filter(
            VoyageDetails.VoyageId == voyage_id
        ).delete(synchronize_session=False)