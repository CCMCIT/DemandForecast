"""Purpose: orchestrate processing of loaded files into Voyage_tbl + VoyageDetails_tbl.

Shared flow, agnostic to the source: the detail repository and mapper are chosen
by the File's FileTypeId via the registry. Each file is one transaction (commit
all -> LoadStatusId = INSERTED_INTO_VOYAGE_DETAIL, or roll back -> ERROR).

- process_file(file_id): process one file.
- process_pending(): process every file with LoadStatusId = INSERTED_INTO_FILE_DETAIL,
  each in its own transaction, skipping types that have no processor yet.
"""
from app.lookups import LoadStatus
from app.db.session import SessionLocal
from app.db.repositories.file_repository import FileRepository
from app.db.repositories.mode_repository import ModeRepository
from app.db.repositories.direction_repository import DirectionRepository
from app.processing.registry import get_processor, has_processor
from app.processing.writer import VoyageWriter


def process_file(file_id: int) -> int:
    session = SessionLocal()
    try:
        file = FileRepository(session).get(file_id)
        if file is None:
            raise ValueError(f"No File with FileId {file_id}")

        detail_repo_cls, map_row = get_processor(file.FileTypeId)
        details = detail_repo_cls(session).get_by_file_id(file_id)

        writer = VoyageWriter(
            session,
            ModeRepository(session).name_to_id(),
            DirectionRepository(session).name_to_id(),
        )
        for detail in details:
            writer.write(map_row(detail))

        file.LoadStatusId = LoadStatus.INSERTED_INTO_VOYAGE_DETAIL
        session.commit()
        return len(details)
    except Exception:
        session.rollback()
        _mark_error(file_id)
        raise
    finally:
        session.close()


def process_pending() -> dict:
    session = SessionLocal()
    try:
        pending = FileRepository(session).get_by_load_status(
            LoadStatus.INSERTED_INTO_FILE_DETAIL
        )
        targets = [(f.FileId, f.FileTypeId) for f in pending]
    finally:
        session.close()

    processed, skipped, failed = [], [], []
    for file_id, file_type_id in targets:
        if not has_processor(file_type_id):
            skipped.append(file_id)  # e.g. NCSPA: no processor registered yet
            continue
        try:
            count = process_file(file_id)
            processed.append((file_id, count))
        except Exception as exc:
            failed.append((file_id, str(exc)))
    return {"processed": processed, "skipped": skipped, "failed": failed}


def _mark_error(file_id: int) -> None:
    session = SessionLocal()
    try:
        file = FileRepository(session).get(file_id)
        if file is not None:
            file.LoadStatusId = LoadStatus.ERROR
            session.commit()
    finally:
        session.close()