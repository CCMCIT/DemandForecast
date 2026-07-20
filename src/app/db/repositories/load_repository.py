"""Repository for Load_tbl. Shared by all companies."""
from app.db.models.load import Load


class LoadRepository:
    def __init__(self, session):
        self.session = session

    def add(self, file: Load) -> Load:
        self.session.add(file)
        self.session.flush()  # assign the identity LoadId
        return file

    def get(self, file_id: int) -> Load | None:
        return self.session.get(Load, file_id)

    def get_by_name(self, file_name: str, exclude_status_id: int | None = None) -> Load | None:
        """Earliest Load row with this name, or None. Pass exclude_status_id to
        ignore rows in that status (e.g. skip failed ERROR attempts)."""
        query = self.session.query(Load).filter(Load.SourceName == file_name)
        if exclude_status_id is not None:
            query = query.filter(Load.LoadStatusId != exclude_status_id)
        return query.order_by(Load.LoadId).first()

    def count(self) -> int:
        return self.session.query(Load).count()

    def count_with_status(self, load_status_id: int) -> int:
        return (
            self.session.query(Load)
            .filter(Load.LoadStatusId == load_status_id)
            .count()
        )

    def get_by_load_status(self, load_status_id: int) -> list[Load]:
        """Ordered by LoadId (ascending) so callers process oldest files first.
        Processing must run oldest->newest: the fall-off classification treats the
        last file that mentions a voyage as authoritative, so out-of-order runs
        would leave the wrong VoyageStatus."""
        return (
            self.session.query(Load)
            .filter(Load.LoadStatusId == load_status_id)
            .order_by(Load.LoadId)
            .all()
        )

    def get_by_type_and_status(self, file_type_id: int, load_status_id: int) -> list[Load]:
        """Files of one type in one load status, oldest first. Used to pick the
        pending files of a single source (e.g. gate activity: type 4, status 2)."""
        return (
            self.session.query(Load)
            .filter(Load.LoadTypeId == file_type_id, Load.LoadStatusId == load_status_id)
            .order_by(Load.LoadId)
            .all()
        )