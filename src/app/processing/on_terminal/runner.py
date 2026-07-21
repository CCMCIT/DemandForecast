"""Purpose: process CMS on-terminal files into OnTermDetail_tbl.

Driven through Load_tbl, like the gate-activity runner: a file carries its LoadTypeId and
LoadStatusId, and processing advances the status. On terminal has no phases -- it reads the
file's staging rows, upserts each by its identity (Date + the two dimension columns), and
moves the file straight from INSERTED_INTO_FILE_DETAIL (2) to INSERTED_INTO_VOYAGE_DETAIL
(4), skipping 3 (a voyage phase it does not have). Status 4 is reused as the terminal "done"
marker for now; the voyage-worded status names/values will be unified in a later refactor.

One transaction per file -- commit all, or roll back, mark the file ERROR, and log. An
existing identity is updated in place; a new identity is inserted, so re-running is
idempotent.

- process_file(file_id): process/reprocess one on-terminal file.
- process_pending(): process every on-terminal file at status 2.
"""
from app.lookups import FileType, LoadStatus
from app.db.session import SessionLocal, session_scope
from app.db.repositories.load_repository import LoadRepository
from app.db.repositories.cms_on_term_detail_repository import CmsOnTermDetailRepository
from app.db.repositories.process_log_error_repository import ProcessLogErrorRepository
from app.processing.on_terminal.mapper import map_row
from app.processing.on_terminal.writer import OnTermWriter


def process_file(file_id: int) -> int:
    """Map an on-terminal file's staging rows into OnTermDetail_tbl, advance the file's
    status to INSERTED_INTO_VOYAGE_DETAIL (4), and return the row count.

    Upserts by identity, so re-running is idempotent. On any failure the whole file rolls
    back, is marked ERROR (99), and the error is logged.
    """
    session = SessionLocal()
    try:
        file = LoadRepository(session).get(file_id)
        if file is None:
            raise ValueError(f"No Load with LoadId {file_id}")
        if file.LoadTypeId != FileType.ON_TERMINAL:
            raise ValueError(
                f"LoadId {file_id} is not an On Terminal file "
                f"(LoadTypeId={file.LoadTypeId})"
            )

        rows = CmsOnTermDetailRepository(session).get_by_file_id(file_id)
        mapped = [map_row(row) for row in rows]

        OnTermWriter(session).write_details(mapped)
        # Advance 2 -> 4 directly; on terminal has no phase 3, so nothing sets 3.
        # Status 4 is reused as the terminal "done" marker for now, matching gate activity;
        # the voyage-worded status names will be unified in a later refactor.
        file.LoadStatusId = LoadStatus.INSERTED_INTO_VOYAGE_DETAIL
        session.commit()
        return len(mapped)
    except Exception as exc:
        session.rollback()
        _mark_error(file_id)
        ProcessLogErrorRepository.write(
            f"On terminal process failed for LoadId {file_id}: {exc}"
        )
        raise
    finally:
        session.close()


def process_pending(progress=None) -> dict:
    """Process every on-terminal file at INSERTED_INTO_FILE_DETAIL (2). One file's failure
    never stops the rest: successes and failures are collected and returned.

    Optional `progress(event, **data)` callback fires for live reporting: 'start' (total),
    then 'processing'/'processed'/'failed' per file. The runner does no printing itself."""
    with session_scope() as session:
        files = LoadRepository(session).get_by_type_and_status(
            FileType.ON_TERMINAL, LoadStatus.INSERTED_INTO_FILE_DETAIL
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


def _mark_error(file_id: int) -> None:
    session = SessionLocal()
    try:
        file = LoadRepository(session).get(file_id)
        if file is not None:
            file.LoadStatusId = LoadStatus.ERROR
            session.commit()
    finally:
        session.close()