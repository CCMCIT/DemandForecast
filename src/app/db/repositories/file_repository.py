"""Repository for File_tbl. Shared by all companies."""
from app.db.models.file import File


class FileRepository:
    def __init__(self, session):
        self.session = session

    def add(self, file: File) -> File:
        self.session.add(file)
        self.session.flush()  # assign the identity FileId
        return file

    def get(self, file_id: int) -> File | None:
        return self.session.get(File, file_id)

    def get_by_name(self, file_name: str, exclude_status_id: int | None = None) -> File | None:
        """Earliest File row with this name, or None. Pass exclude_status_id to
        ignore rows in that status (e.g. skip failed ERROR attempts)."""
        query = self.session.query(File).filter(File.FileName == file_name)
        if exclude_status_id is not None:
            query = query.filter(File.LoadStatusId != exclude_status_id)
        return query.order_by(File.FileId).first()

    def count(self) -> int:
        return self.session.query(File).count()

    def count_with_status(self, load_status_id: int) -> int:
        return (
            self.session.query(File)
            .filter(File.LoadStatusId == load_status_id)
            .count()
        )

    def get_by_load_status(self, load_status_id: int) -> list[File]:
        """Ordered by FileId (ascending) so callers process oldest files first.
        Processing must run oldest->newest: the fall-off classification treats the
        last file that mentions a voyage as authoritative, so out-of-order runs
        would leave the wrong VoyageStatus."""
        return (
            self.session.query(File)
            .filter(File.LoadStatusId == load_status_id)
            .order_by(File.FileId)
            .all()
        )