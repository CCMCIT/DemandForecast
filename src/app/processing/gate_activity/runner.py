"""Purpose: process CMS gate-activity files into GateActivityDetail_tbl.

Driven through File_tbl, like the voyage runner: a file carries its FileTypeId and
LoadStatusId, and processing advances the status. Gate activity has no phases -- it
reads the file's staging rows, upserts each by its identity (Date + the nine dimension
columns), and moves the file straight from INSERTED_INTO_FILE_DETAIL (2) to
INSERTED_INTO_VOYAGE_DETAIL (4). (That status name is shared with voyages and will be
renamed to a neutral "Inserted into Detail" once both sources use it.)

One transaction per file -- commit all, or roll back, mark the file ERROR, and log. An
existing identity is updated in place (same id, prior version archived by temporal); a
new identity is inserted, so re-running is idempotent.

- process_file(file_id): process/reprocess one gate-activity file.
- process_pending(): process every gate-activity file at status 2.
"""
from app.lookups import FileType, LoadStatus
from app.db.session import SessionLocal, session_scope
from app.db.repositories.file_repository import FileRepository
from app.db.repositories.cms_gate_activity_detail_repository import CmsGateActivityDetailRepository
from app.db.repositories.gate_type_repository import GateTypeRepository
from app.db.repositories.process_log_error_repository import ProcessLogErrorRepository
from app.processing.gate_activity.mapper import map_row
from app.processing.gate_activity.writer import GateActivityWriter


class InvalidGateActivityError(Exception):
    """A file's mapped rows failed prevalidation; the file must not be processed."""


def process_file(file_id: int) -> int:
    """Map a gate-activity file's staging rows into GateActivityDetail_tbl, advance the
    file's status to INSERTED_INTO_VOYAGE_DETAIL (4), and return the row count.

    Upserts by identity, so re-running is idempotent. On any failure the whole file
    rolls back, is marked ERROR (99), and the error is logged.
    """
    session = SessionLocal()
    try:
        file = FileRepository(session).get(file_id)
        if file is None:
            raise ValueError(f"No File with FileId {file_id}")
        if file.FileTypeId != FileType.GATE_ACTIVITIES:
            raise ValueError(
                f"FileId {file_id} is not a Gate Activities file "
                f"(FileTypeId={file.FileTypeId})"
            )

        rows = CmsGateActivityDetailRepository(session).get_by_file_id(file_id)
        mapped = [map_row(row) for row in rows]

        # Reject the whole file up front if any gate type is unknown. GateTypeId has no
        # FK in the DB, so this is the only guard against a bad value slipping through.
        _validate_gate_types(mapped, GateTypeRepository(session).id_set())

        GateActivityWriter(session).write_details(mapped)
        file.LoadStatusId = LoadStatus.INSERTED_INTO_VOYAGE_DETAIL  # 2 -> 4 (detail written)
        session.commit()
        return len(mapped)
    except Exception as exc:
        session.rollback()
        _mark_error(file_id)
        ProcessLogErrorRepository.write(
            f"Gate activity process failed for FileId {file_id}: {exc}"
        )
        raise
    finally:
        session.close()


def process_pending() -> dict:
    """Process every gate-activity file at INSERTED_INTO_FILE_DETAIL (2). One file's
    failure never stops the rest: successes and failures are collected and returned."""
    with session_scope() as session:
        files = FileRepository(session).get_by_type_and_status(
            FileType.GATE_ACTIVITIES, LoadStatus.INSERTED_INTO_FILE_DETAIL
        )
        targets = [f.FileId for f in files]

    processed, failed = [], []
    for file_id in targets:
        try:
            count = process_file(file_id)
            processed.append((file_id, count))
        except Exception as exc:
            failed.append((file_id, str(exc)))
    return {"processed": processed, "failed": failed}


def _validate_gate_types(mapped, valid_ids: set[int]) -> None:
    """Raise if any row names a GateTypeId the GateType lookup does not have."""
    unknown = sorted(
        {m.gate_type_id for m in mapped
         if m.gate_type_id is not None and m.gate_type_id not in valid_ids}
    )
    if unknown:
        raise InvalidGateActivityError(f"unknown GateTypeId(s): {unknown}")


def _mark_error(file_id: int) -> None:
    session = SessionLocal()
    try:
        file = FileRepository(session).get(file_id)
        if file is not None:
            file.LoadStatusId = LoadStatus.ERROR
            session.commit()
    finally:
        session.close()