"""Purpose: orchestrate processing of loaded files into Voyage_tbl, VoyageDetails_tbl,
and the field-mapping tables.

Shared flow, agnostic to the source: the detail repository and mapper are chosen by
the File's FileTypeId via the registry. Each file is processed in three committed
phases, each atomic across the whole file, so an interrupted run resumes from the
last completed phase without losing or duplicating work:

  Phase 1 - insert every voyage,   commit, LoadStatusId = INSERTED_INTO_VOYAGE (3).
  Phase 2 - insert every detail,   commit, LoadStatusId = INSERTED_INTO_VOYAGE_DETAIL (4).
  Phase 3 - write every field map, commit, LoadStatusId = INSERTED_INTO_FIELD_MAP (5).
            (field maps go through the DemandForecast.VoyageFieldMap_upsert proc)

On resume, the file's LoadStatusId says which phases are already committed: those are
skipped and the already-saved voyages are loaded so only the remaining phases run.
A user stop (Ctrl+C) rolls back the current phase and leaves the status at the last
committed phase. A real exception rolls back, sets ERROR (99), and logs to
Process_Log_Error_tbl; a file left at ERROR is reprocessed from phase 1.

- process_file(file_id): process/resume one file across the three phases.
- process_pending(): process every file at status 2 (new), 3 or 4 (resume),
  skipping types with no processor yet.
- process_next(count): process the next `count` pending files (same order).
"""
from app.lookups import FieldType, LoadStatus
from app.db.session import SessionLocal, session_scope
from app.db.repositories.file_repository import FileRepository
from app.db.repositories.process_log_error_repository import ProcessLogErrorRepository
from app.db.repositories.mode_repository import ModeRepository
from app.db.repositories.direction_repository import DirectionRepository
from app.db.repositories.field_type_value_repository import FieldTypeValueRepository
from app.db.repositories.voyage_repository import VoyageRepository
from app.processing.voyage.registry import get_processor, has_processor
from app.processing.voyage.status import classify
from app.processing.voyage.validation import validate_voyages
from app.processing.voyage.writer import VoyageWriter


class AlreadyProcessedError(Exception):
    """Raised when a file was already fully processed (LoadStatusId=5)."""


def process_file(file_id: int, progress=None) -> int:
    _reject_if_already_processed(file_id)  # fail fast, before the transaction

    session = SessionLocal()
    try:
        file = FileRepository(session).get(file_id)
        detail_repo_cls, map_row = get_processor(file.FileTypeId)
        rows = detail_repo_cls(session).get_by_file_id(file_id)

        # The lookup maps are loaded once per file (name -> id) and handed to the
        # writer, so resolving a name costs no DB hit per row.
        equipment_ids = FieldTypeValueRepository(session).value_to_id(FieldType.EQUIPMENT_TYPE)
        writer = VoyageWriter(
            session,
            ModeRepository(session).name_to_id(),
            DirectionRepository(session).name_to_id(),
            equipment_ids,
        )
        mapped = [map_row(row) for row in rows]

        # Reject the whole file up front if any row is unusable, before any write.
        # On failure the except below rolls back (nothing written), marks the file
        # ERROR, and logs -- so a bad file is skipped, not partially processed.
        validate_voyages(mapped, set(equipment_ids))

        # Resume from where a previous run stopped. The file's LoadStatusId says
        # which phases are already committed, so we skip those and only run what's
        # left. A file at ERROR (99) is reprocessed from phase 1 (idempotent).
        status = file.LoadStatusId
        voyages_done = status in (
            LoadStatus.INSERTED_INTO_VOYAGE,
            LoadStatus.INSERTED_INTO_VOYAGE_DETAIL,
        )
        details_done = status == LoadStatus.INSERTED_INTO_VOYAGE_DETAIL

        # Phase 1: voyages. If already committed (resume), load them instead of
        # rewriting -- avoids duplicate work and spurious temporal-history versions.
        if voyages_done:
            voyages = writer.load_voyages(mapped)
            _report(progress, "phase", number=1, name="voyages", state="skipped")
        else:
            voyages = [writer.write_voyage(m) for m in mapped]
            file.LoadStatusId = LoadStatus.INSERTED_INTO_VOYAGE
            session.commit()
            _report(progress, "phase", number=1, name="voyages", state="completed")

        # Phase 2: details (skip if already committed).
        if not details_done:
            for m, voyage in zip(mapped, voyages):
                writer.write_details(m, voyage)
            file.LoadStatusId = LoadStatus.INSERTED_INTO_VOYAGE_DETAIL
            session.commit()
            _report(progress, "phase", number=2, name="details", state="completed")
        else:
            _report(progress, "phase", number=2, name="details", state="skipped")

        # Phase 3: field maps via the proc. Always runs here -- the only "phase 3
        # done" state (5) is rejected up front by _reject_if_already_processed.
        for m, voyage in zip(mapped, voyages):
            writer.write_fields(m, voyage)
        file.LoadStatusId = LoadStatus.INSERTED_INTO_FIELD_MAP
        session.commit()
        _report(progress, "phase", number=3, name="field maps", state="completed")

        # Voyages still marked ToCall but absent from this file have fallen off the
        # report -> classify each as Called or Cancelled. Own commit; a failure
        # here is logged but does not undo the already-processed file.
        _classify_fallen_off(session, {r.VOYAGE for r in rows}, detail_repo_cls, file_id)
        return len(rows)
    except KeyboardInterrupt:
        # User stop: discard the current uncommitted phase and leave the status at
        # the last committed phase, so the next run resumes from there.
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


def process_pending(progress=None, limit=None) -> dict:
    """Process pending files. Optional `progress(event, **data)` callback is fired
    for live reporting: 'start' (total), then 'processing'/'processed'/'skipped'/
    'failed' per file. The runner does no printing itself.

    `limit` caps how many files are taken (the first N in priority order); None
    means all. process_next is the named entry point for the "next N files" case."""
    with session_scope() as session:
        repo = FileRepository(session)
        # Most-complete first so interrupted files finish before new ones start:
        # status 4 (details in, field maps not) -> 3 (voyages in, details not) -> 2 (new).
        files = repo.get_by_load_status(LoadStatus.INSERTED_INTO_VOYAGE_DETAIL) + \
            repo.get_by_load_status(LoadStatus.INSERTED_INTO_VOYAGE) + \
            repo.get_by_load_status(LoadStatus.INSERTED_INTO_FILE_DETAIL)
        targets = [(f.FileId, f.FileTypeId) for f in files]
        if limit is not None:
            targets = targets[:limit]  # the next N in priority order

    _report(progress, "start", total=len(targets))

    processed, skipped, failed = [], [], []
    for file_id, file_type_id in targets:
        if not has_processor(file_type_id):
            skipped.append(file_id)  # e.g. NCSPA: no processor registered yet
            _report(progress, "skipped", file_id=file_id)
            continue
        _report(progress, "processing", file_id=file_id)
        try:
            count = process_file(file_id, progress=progress)
            processed.append((file_id, count))
            _report(progress, "processed", file_id=file_id, count=count)
        except Exception as exc:
            failed.append((file_id, str(exc)))
            _report(progress, "failed", file_id=file_id, error=str(exc))
    return {"processed": processed, "skipped": skipped, "failed": failed}


def process_next(count: int, progress=None) -> dict:
    """Process the next `count` pending files, in the same priority order as
    process_pending (status 4, then 3, then 2). A thin cap over process_pending;
    files whose type has no processor still count toward `count` (reported as
    skipped)."""
    return process_pending(progress=progress, limit=count)


def _classify_fallen_off(session, in_file_voyages, detail_repo_cls, file_id) -> None:
    """Classify voyages that dropped off the report. Any voyage still marked
    ToCall that is not in the file just processed has fallen off; set it Called or
    Cancelled from its own last reported date vs its work date. Runs in its own
    commit and swallows errors -- the file itself is already processed.

    The reported dates for all fallen-off voyages are fetched in ONE query
    (get_reported_dates) rather than one query per voyage."""
    try:
        detail_repo = detail_repo_cls(session)
        voyages = VoyageRepository(session).get_tocall_not_in(in_file_voyages)
        reported_dates = detail_repo.get_reported_dates(
            [(v.FileId, v.Voyage) for v in voyages]
        )
        for voyage in voyages:
            reported_date = reported_dates.get((voyage.FileId, voyage.Voyage))
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
    if file.LoadStatusId == LoadStatus.INSERTED_INTO_FIELD_MAP:
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