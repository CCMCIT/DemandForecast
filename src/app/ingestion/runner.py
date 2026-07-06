"""Shared ingestion flow: file on disk -> raw company table.

One transaction per file: commit all with LoadStatusId = INSERTED_INTO_FILE_DETAIL,
or roll back and record the File row with LoadStatusId = ERROR. Entrypoints call
run(); the flow does not know how it was triggered.
"""
import os

from app.lookups import LoadStatus
from app.db.session import SessionLocal, session_scope
from app.db.models.file import File
from app.db.repositories.file_repository import FileRepository
from app.db.repositories.process_log_error_repository import ProcessLogErrorRepository
from app.ingestion.registry import get_handlers


class FileAlreadyIngestedError(Exception):
    """Raised when a file with this name was already loaded (not an ERROR row)."""


def run(file_type_id: int, path: str) -> int:
    reader_cls, loader_cls = get_handlers(file_type_id)
    file_name = os.path.basename(path)

    _reject_if_already_inserted(file_name)  # fail fast, before reading/transaction
    rows = reader_cls().read(path)

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
    except Exception as exc:
        session.rollback()
        _record_failure(session, file_name, file_type_id)
        ProcessLogErrorRepository.write(f"Ingest failed for '{file_name}': {exc}")
        raise
    finally:
        session.close()


def run_folder(file_type_id: int, folder: str, progress=None) -> dict:
    """Ingest every file in a folder, each in its own transaction.

    One file's outcome never stops the rest: already-loaded files are skipped,
    failures are recorded (and logged by run()), successes return a FileId.
    Optional `progress(event, **data)` callback fires 'start' (total), then
    'ingesting'/'ingested'/'skipped'/'failed' per file. The runner never prints.
    """
    paths = _list_files(folder)
    _report(progress, "start", total=len(paths))

    ingested, skipped, failed = [], [], []
    for path in paths:
        file_name = os.path.basename(path)
        _report(progress, "ingesting", file_name=file_name)
        try:
            file_id = run(file_type_id, path)
            ingested.append((file_name, file_id))
            _report(progress, "ingested", file_name=file_name, file_id=file_id)
        except FileAlreadyIngestedError:
            skipped.append(file_name)
            _report(progress, "skipped", file_name=file_name)
        except Exception as exc:
            failed.append((file_name, str(exc)))
            _report(progress, "failed", file_name=file_name, error=str(exc))
    return {"ingested": ingested, "skipped": skipped, "failed": failed}


def _report(progress, event, **data) -> None:
    if progress is not None:
        progress(event, **data)


def import_summary() -> dict:
    """Count files imported successfully (any non-ERROR File row) out of all
    File rows. A failed ingest leaves an ERROR row, so total = imported + failed."""
    with session_scope() as session:
        repo = FileRepository(session)
        total = repo.count()
        failed = repo.count_with_status(LoadStatus.ERROR)
    return {"total": total, "imported": total - failed, "failed": failed}


def _list_files(folder: str) -> list[str]:
    if not os.path.isdir(folder):
        raise ValueError(f"Folder not found: {folder}")
    return [
        os.path.join(folder, name)
        for name in sorted(os.listdir(folder))
        # Skip Excel temp lock files (~$Book.xlsx), created while a workbook is
        # open; they aren't real inputs and would only fail ingestion.
        if os.path.isfile(os.path.join(folder, name)) and not name.startswith("~$")
    ]


def _reject_if_already_inserted(file_name: str) -> None:
    """Block re-ingesting a file already loaded. Ignores prior ERROR rows so a
    failed attempt can be retried. Raised before any transaction, so it creates
    no File row and no error-log entry — it's a validation rejection."""
    with session_scope() as session:
        existing = FileRepository(session).get_by_name(
            file_name, exclude_status_id=LoadStatus.ERROR
        )
    if existing is not None:
        raise FileAlreadyIngestedError(
            f"File name: {file_name} is already inserted with id: {existing.FileId}"
        )


def _record_failure(session, file_name: str, file_type_id: int) -> None:
    session.add(
        File(
            FileName=file_name,
            FileTypeId=file_type_id,
            LoadStatusId=LoadStatus.ERROR,
        )
    )
    session.commit()