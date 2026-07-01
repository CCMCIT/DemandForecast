"""Shared ingestion flow: file on disk -> raw company table.

One transaction per file: commit all with LoadStatusId = INSERTED_INTO_FILE_DETAIL,
or roll back and record the File row with LoadStatusId = ERROR. Entrypoints call
run(); the flow does not know how it was triggered.
"""
import os

from app.lookups import LoadStatus
from app.db.session import SessionLocal
from app.db.models.file import File
from app.db.repositories.file_repository import FileRepository
from app.ingestion.registry import get_handlers


def run(file_type_id: int, path: str) -> int:
    reader_cls, loader_cls = get_handlers(file_type_id)
    rows = reader_cls().read(path)
    file_name = os.path.basename(path)

    session = SessionLocal()
    try:
        file = File(
            FileName=file_name,
            FileTypeId=file_type_id,
            LoadStatusId=LoadStatus.INSERTED_INTO_FILE,
        )
        FileRepository(session).add(file)            # flush -> FileId
        loader_cls().load(session, file.FileId, rows)
        file.LoadStatusId = LoadStatus.INSERTED_INTO_FILE_DETAIL
        session.commit()                             # commit File + all detail rows together
        return file.FileId
    except Exception:
        session.rollback()
        _record_failure(session, file_name, file_type_id)
        raise
    finally:
        session.close()


def _record_failure(session, file_name: str, file_type_id: int) -> None:
    session.add(
        File(
            FileName=file_name,
            FileTypeId=file_type_id,
            LoadStatusId=LoadStatus.ERROR,
        )
    )
    session.commit()