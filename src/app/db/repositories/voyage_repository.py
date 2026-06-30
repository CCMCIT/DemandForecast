"""Repository for Voyage_tbl. Shared target."""
from app.db.models.voyage import Voyage


class VoyageRepository:
    def __init__(self, session):
        self.session = session

    def add(self, voyage: Voyage) -> Voyage:
        self.session.add(voyage)
        self.session.flush()  # assign the identity VoyageId
        return voyage