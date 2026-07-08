"""Repository for Voyage_tbl. Shared target."""
from app.db.models.voyage import Voyage
from app.lookups import VoyageStatus


class VoyageRepository:
    def __init__(self, session):
        self.session = session

    def add(self, voyage: Voyage) -> Voyage:
        self.session.add(voyage)
        self.session.flush()  # assign the identity VoyageId
        return voyage

    def get_by_voyage(self, voyage: str) -> Voyage | None:
        """The existing row with this Voyage number, or None. Voyage is unique."""
        return (
            self.session.query(Voyage)
            .filter(Voyage.Voyage == voyage)
            .one_or_none()
        )

    def get_tocall_not_in(self, voyage_numbers) -> list[Voyage]:
        """ToCall voyages whose number is NOT in the given set -- i.e. voyages
        that have fallen off the report represented by that set of numbers."""
        query = self.session.query(Voyage).filter(
            Voyage.VoyageStatusId == VoyageStatus.TO_CALL
        )
        if voyage_numbers:
            query = query.filter(Voyage.Voyage.notin_(voyage_numbers))
        return query.all()