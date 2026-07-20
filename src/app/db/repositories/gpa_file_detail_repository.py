"""Repository for GpaFileDetail_tbl (GPA raw rows)."""
from datetime import date, datetime

from app.db.models.gpa_file_detail import GpaFileDetail


def _parse_reported(reported: str | None) -> date | None:
    """Parse a REPORTED value (MMDDYYYY string, e.g. '07032025') to a date, or
    None if it is absent, blank, or unparseable."""
    if not reported:
        return None
    try:
        return datetime.strptime(reported.strip(), "%m%d%Y").date()
    except ValueError:
        return None


class GpaFileDetailRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, details: list[GpaFileDetail]) -> None:
        self.session.add_all(details)

    def get_by_file_id(self, file_id: int) -> list[GpaFileDetail]:
        return (
            self.session.query(GpaFileDetail)
            .filter(GpaFileDetail.LoadId == file_id)
            .all()
        )

    def get_reported_date(self, file_id: int, voyage: str) -> date | None:
        """The parsed REPORTED date for a voyage's row in a given file, or None."""
        row = (
            self.session.query(GpaFileDetail.REPORTED)
            .filter(GpaFileDetail.LoadId == file_id, GpaFileDetail.VOYAGE == voyage)
            .first()
        )
        return _parse_reported(row.REPORTED) if row is not None else None

    def get_reported_dates(
        self, file_voyage_pairs: list[tuple[int, str]]
    ) -> dict[tuple[int, str], date]:
        """Batch form of get_reported_date: {(LoadId, Voyage): date} for the given
        (LoadId, Voyage) pairs, fetched in ONE query instead of one per pair.

        A pair whose REPORTED is absent/blank/unparseable is simply omitted, so the
        caller treats a missing key exactly like get_reported_date returning None.
        """
        if not file_voyage_pairs:
            return {}
        wanted = set(file_voyage_pairs)
        file_ids = {file_id for file_id, _ in file_voyage_pairs}
        voyage_nums = {voyage for _, voyage in file_voyage_pairs}
        # Filter by the two column sets, then keep only the exact pairs asked for
        # (a LoadId/Voyage cross-combination that isn't a wanted pair is discarded).
        rows = (
            self.session.query(
                GpaFileDetail.LoadId, GpaFileDetail.VOYAGE, GpaFileDetail.REPORTED
            )
            .filter(
                GpaFileDetail.LoadId.in_(file_ids),
                GpaFileDetail.VOYAGE.in_(voyage_nums),
            )
            .all()
        )
        result: dict[tuple[int, str], date] = {}
        for file_id, voyage, reported in rows:
            key = (file_id, voyage)
            if key not in wanted:
                continue
            parsed = _parse_reported(reported)
            if parsed is not None:
                result[key] = parsed
        return result
