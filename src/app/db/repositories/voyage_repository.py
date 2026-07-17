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

    def get_by_voyage_numbers(self, voyage_numbers) -> dict[str, Voyage]:
        """The existing Voyage rows for these numbers, keyed by number. Used on
        resume to fetch the already-saved voyages in one query (Voyage is unique)."""
        if not voyage_numbers:
            return {}
        rows = (
            self.session.query(Voyage)
            .filter(Voyage.Voyage.in_(set(voyage_numbers)))
            .all()
        )
        return {v.Voyage: v for v in rows}

    def get_tocall_not_in(self, voyage_numbers) -> list[Voyage]:
        """ToCall voyages whose number is NOT in the given set -- i.e. voyages
        that have fallen off the report represented by that set of numbers."""
        query = self.session.query(Voyage).filter(
            Voyage.VoyageStatusId == VoyageStatus.TO_CALL
        )
        if voyage_numbers:
            query = query.filter(Voyage.Voyage.notin_(voyage_numbers))
        return query.all()