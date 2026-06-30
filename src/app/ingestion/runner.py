"""Shared ingestion flow: file on disk -> raw company table.

One transaction per file: commit all, or roll back and record the File row with
LoadStatus = False (FAILED). Entrypoints call run(); the flow does not know how
it was triggered.
"""
import os

from app.db.session import SessionLocal
from app.db.models.file import File
from app.db.repositories.file_repository import FileRepository
from app.ingestion.registry import get_handlers


def run(file_type: str, path: str) -> int:
    reader_cls, loader_cls = get_handlers(file_type)
    rows = reader_cls().read(path)
    file_name = os.path.basename(path)

    session = SessionLocal()
    try:
        file = File(FileName=file_name, FileType=file_type, LoadStatus=False)
        FileRepository(session).add(file)            # flush -> FileId
        loader_cls().load(session, file.FileId, rows)
        file.LoadStatus = True
        session.commit()                             # commit File + all detail rows together
        return file.FileId
    except Exception:
        session.rollback()
        _record_failure(session, file_name, file_type)
        raise
    finally:
        session.close()


def _record_failure(session, file_name: str, file_type: str) -> None:
    session.add(File(FileName=file_name, FileType=file_type, LoadStatus=False))
    session.commit()