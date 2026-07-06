"""Purpose: orchestrate processing of loaded files into Voyage_tbl + VoyageDetails_tbl.

Shared flow, agnostic to the source: the detail repository and mapper are chosen
by the File's FileTypeId via the registry. Each file is processed in two committed
phases so an interrupted run can resume without losing or duplicating work:

  Phase 1 - insert every voyage, commit, set LoadStatusId = INSERTED_INTO_VOYAGE (3).
  Phase 2 - insert every detail in one commit (all-or-none), set
            LoadStatusId = INSERTED_INTO_VOYAGE_DETAIL (4).

If phase 2 is interrupted its transaction rolls back, so no detail is written and
the file stays at status 3: next run finds the voyages already there and re-runs
phase 2 only. A user stop (Ctrl+C) prints a notice and leaves the status as-is; a
real exception rolls back, sets ERROR (5), and logs to Process_Log_Error_tbl.

- process_file(file_id): process one file across both phases.
- process_pending(): process every file at INSERTED_INTO_FILE_DETAIL (2, new) or
  INSERTED_INTO_VOYAGE (3, resume), skipping types with no processor yet.
"""
from app.lookups import LoadStatus
from app.db.session import SessionLocal, session_scope
from app.db.repositories.file_repository import FileRepository
from app.db.repositories.process_log_error_repository import ProcessLogErrorRepository
from app.db.repositories.mode_repository import ModeRepository
from app.db.repositories.direction_repository import DirectionRepository
from app.db.repositories.voyage_repository import VoyageRepository
from app.processing.registry import get_processor, has_processor
from app.processing.status import classify
from app.processing.writer import VoyageWriter


class AlreadyProcessedError(Exception):
    """Raised when a file was already processed into voyages (LoadStatusId=4)."""


def process_file(file_id: int) -> int:
    _reject_if_already_processed(file_id)  # fail fast, before the transaction

    session = SessionLocal()
    try:
        file = FileRepository(session).get(file_id)
        detail_repo_cls, map_row = get_processor(file.FileTypeId)
        rows = detail_repo_cls(session).get_by_file_id(file_id)

        writer = VoyageWriter(
            session,
            ModeRepository(session).name_to_id(),
            DirectionRepository(session).name_to_id(),
        )
        mapped = [map_row(row) for row in rows]

        # Phase 1: voyages only. On resume (status 3) these already exist, so the
        # writer replaces them in place instead of inserting duplicates.
        voyages = [writer.write_voyage(m) for m in mapped]
        file.LoadStatusId = LoadStatus.INSERTED_INTO_VOYAGE
        session.commit()

        # Phase 2: all details in a single transaction. If it is interrupted the
        # rollback leaves zero details, so the file stays at status 3 and phase 2
        # is safely re-run next time.
        for m, voyage in zip(mapped, voyages):
            writer.write_details(m, voyage)
        file.LoadStatusId = LoadStatus.INSERTED_INTO_VOYAGE_DETAIL
        session.commit()

        # Voyages still marked ToCall but absent from this file have fallen off the
        # report -> classify each as Called or Cancelled. Own commit; a failure
        # here is logged but does not undo the already-processed file.
        _classify_fallen_off(session, {r.VOYAGE for r in rows}, detail_repo_cls, file_id)
        return len(rows)
    except KeyboardInterrupt:
        # User stop: discard any partial phase-2 details and leave the status
        # untouched (3 if phase 1 committed, else 2) so the file resumes later.
        session.rollback()
        print("user requested stop")
        raise
    except Exception as exc:
        session.rollback()
        _mark_error(file_id)
        ProcessLogErrorRepository.write(f"Process failed for FileId {file_id}: {exc}")
        raise
    finally:
        session.close()


def process_pending(progress=None) -> dict:
    """Process every pending file. Optional `progress(event, **data)` callback
    is fired for live reporting: 'start' (total), then 'processing'/'processed'/
    'skipped'/'failed' per file. The runner does no printing itself."""
    with session_scope() as session:
        repo = FileRepository(session)
        # Status 3 first: finish files whose voyages are in but details are not,
        # then status 2: files not yet started.
        files = repo.get_by_load_status(LoadStatus.INSERTED_INTO_VOYAGE) + \
            repo.get_by_load_status(LoadStatus.INSERTED_INTO_FILE_DETAIL)
        targets = [(f.FileId, f.FileTypeId) for f in files]

    _report(progress, "start", total=len(targets))

    processed, skipped, failed = [], [], []
    for file_id, file_type_id in targets:
        if not has_processor(file_type_id):
            skipped.append(file_id)  # e.g. NCSPA: no processor registered yet
            _report(progress, "skipped", file_id=file_id)
            continue
        _report(progress, "processing", file_id=file_id)
        try:
            count = process_file(file_id)
            processed.append((file_id, count))
            _report(progress, "processed", file_id=file_id, count=count)
        except Exception as exc:
            failed.append((file_id, str(exc)))
            _report(progress, "failed", file_id=file_id, error=str(exc))
    return {"processed": processed, "skipped": skipped, "failed": failed}


def _classify_fallen_off(session, in_file_voyages, detail_repo_cls, file_id) -> None:
    """Classify voyages that dropped off the report. Any voyage still marked
    ToCall that is not in the file just processed has fallen off; set it Called or
    Cancelled from its own last reported date vs its work date. Runs in its own
    commit and swallows errors -- the file itself is already processed."""
    try:
        detail_repo = detail_repo_cls(session)
        voyages = VoyageRepository(session)
        for voyage in voyages.get_tocall_not_in(in_file_voyages):
            reported_date = detail_repo.get_reported_date(voyage.FileId, voyage.Voyage)
            if reported_date is None or voyage.WORK_DATE is None:
                continue  # cannot classify without both dates
            voyage.VoyageStatusId = classify(voyage.WORK_DATE, reported_date)
        session.commit()
    except Exception as exc:
        session.rollback()
        ProcessLogErrorRepository.write(
            f"Fallen-off classification failed after FileId {file_id}: {exc}"
        )


def _report(progress, event, **data) -> None:
    if progress is not None:
        progress(event, **data)


def _reject_if_already_processed(file_id: int) -> None:
    """Refuse to re-process a file already turned into voyages. Raised before any
    transaction, so it neither marks the file ERROR nor writes an error-log row —
    it's a validation rejection, not a failure."""
    with session_scope() as session:
        file = FileRepository(session).get(file_id)
    if file is None:
        raise ValueError(f"No File with FileId {file_id}")
    if file.LoadStatusId == LoadStatus.INSERTED_INTO_VOYAGE_DETAIL:
        raise AlreadyProcessedError(
            f"FileId {file_id} is already processed (LoadStatusId={file.LoadStatusId})."
        )


def _mark_error(file_id: int) -> None:
    session = SessionLocal()
    try:
        file = FileRepository(session).get(file_id)
        if file is not None:
            file.LoadStatusId = LoadStatus.ERROR
            session.commit()
    finally:
        session.close()