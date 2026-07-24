"""Repository for GpaFileDetail_tbl (GPA raw rows)."""
from datetime import datetime

from app.db.models.gpa_file_detail import GpaFileDetail


def _parse_reported(reported: str | None) -> datetime:
    """Parse a REPORTED value into a datetime, keeping the time.

    Accepts 'MMDDYYYY' (-> midnight) and 'MMDDYYYYHHMM' (e.g. '071020261348'
    -> 2026-07-10 13:48). Raises ValueError, naming the value, on anything blank
    or unreadable; callers either surface that (a new file is rejected) or skip
    the row (old data read back from the DB).
    """
    text = (reported or "").strip()
    for fmt in ("%m%d%Y%H%M", "%m%d%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"unreadable REPORTED value: {reported!r}")


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

    def get_reported_dates(
        self, file_voyage_pairs: list[tuple[int, str]]
    ) -> dict[tuple[int, str], datetime]:
        """Parsed REPORTED for each (LoadId, Voyage), read from the DB in ONE query.

        Reads dates back for old voyages already stored (the fallen-off
        classification). A row that is missing, blank, or unreadable is skipped, so
        one bad legacy row cannot crash the sweep. New files are validated up front
        by validate_voyages, not here.
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
        result: dict[tuple[int, str], datetime] = {}
        for file_id, voyage, reported in rows:
            key = (file_id, voyage)
            if key not in wanted:
                continue
            try:
                result[key] = _parse_reported(reported)
            except ValueError:
                continue  # blank/unreadable legacy row -> skip; the caller can't date it
        return result
