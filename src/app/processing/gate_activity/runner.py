"""Purpose: process CMS gate-activity files into GateActivityDetail_tbl.

Driven through Load_tbl, like the voyage runner: a file carries its LoadTypeId and
LoadStatusId, and processing advances the status. Gate activity has no phases -- it
reads the file's staging rows, upserts each by its identity (Date + the nine dimension
columns), and moves the file straight from INSERTED_INTO_FILE_DETAIL (2) to
INSERTED_INTO_VOYAGE_DETAIL (4), skipping 3 (a voyage phase it does not have). Status 4
is reused as the terminal "done" marker for now; the voyage-worded status names/values
will be unified in a later refactor (see process_file).

One transaction per file -- commit all, or roll back, mark the file ERROR, and log. An
existing identity is updated in place (same id, prior version archived by temporal); a
new identity is inserted, so re-running is idempotent.

- process_file(file_id): process/reprocess one gate-activity file.
- process_pending(): process every gate-activity file at status 2.
"""
from app.lookups import FileType, LoadStatus
from app.db.session import SessionLocal, session_scope
from app.db.repositories.load_repository import LoadRepository
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
        file = LoadRepository(session).get(file_id)
        if file is None:
            raise ValueError(f"No Load with LoadId {file_id}")
        if file.LoadTypeId != FileType.GATE_ACTIVITIES:
            raise ValueError(
                f"LoadId {file_id} is not a Gate Activities file "
                f"(LoadTypeId={file.LoadTypeId})"
            )

        rows = CmsGateActivityDetailRepository(session).get_by_file_id(file_id)
        mapped = [map_row(row) for row in rows]

        # Reject the whole file up front if any gate type is unknown. GateTypeId has no
        # FK in the DB, so this is the only guard against a bad value slipping through.
        _validate_gate_types(mapped, GateTypeRepository(session).id_set())

        GateActivityWriter(session).write_details(mapped)
        # Advance 2 -> 4 directly; gate activity has no phase 3, so nothing sets 3.
        # Status 4 is reused as the terminal "done" marker for now. Arguably this should
        # be 5 ("fully processed"), since the file IS fully done after the upsert -- kept
        # at 4 pending a later refactor that unifies the voyage-worded status names.
        file.LoadStatusId = LoadStatus.INSERTED_INTO_VOYAGE_DETAIL
        session.commit()
        return len(mapped)
    except Exception as exc:
        session.rollback()
        _mark_error(file_id)
        ProcessLogErrorRepository.write(
            f"Gate activity process failed for LoadId {file_id}: {exc}"
        )
        raise
    finally:
        session.close()


def process_pending(progress=None) -> dict:
    """Process every gate-activity file at INSERTED_INTO_FILE_DETAIL (2). One file's
    failure never stops the rest: successes and failures are collected and returned.

    Optional `progress(event, **data)` callback fires for live reporting: 'start'
    (total), then 'processing'/'processed'/'failed' per file. The runner does no
    printing itself."""
    with session_scope() as session:
        files = LoadRepository(session).get_by_type_and_status(
            FileType.GATE_ACTIVITIES, LoadStatus.INSERTED_INTO_FILE_DETAIL
        )
        targets = [f.LoadId for f in files]

    _report(progress, "start", total=len(targets))

    processed, failed = [], []
    for file_id in targets:
        _report(progress, "processing", file_id=file_id)
        try:
            count = process_file(file_id)
            processed.append((file_id, count))
            _report(progress, "processed", file_id=file_id, count=count)
        except Exception as exc:
            failed.append((file_id, str(exc)))
            _report(progress, "failed", file_id=file_id, error=str(exc))
    return {"processed": processed, "failed": failed}


def _report(progress, event, **data) -> None:
    if progress is not None:
        progress(event, **data)


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
        file = LoadRepository(session).get(file_id)
        if file is not None:
            file.LoadStatusId = LoadStatus.ERROR
            session.commit()
    finally:
        session.close()