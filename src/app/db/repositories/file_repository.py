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

    def get_by_load_status(self, load_status_id: int) -> list[File]:
        return (
            self.session.query(File)
            .filter(File.LoadStatusId == load_status_id)
            .all()
        )