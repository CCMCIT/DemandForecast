"""Purpose: process one file's CMS gate-activity staging rows into GateActivityDetail_tbl.

A single committed step: read the staging rows, map them, validate, then upsert each row
by its identity (Date + the nine dimension columns). A row whose identity already exists
is updated in place (same id, prior version archived by temporal); a new identity is
inserted. One transaction for the whole file -- commit all, or roll back and log. Unlike
the voyage runner there are no phases or LoadStatus: gate activity is a straight 1:1
translation, not a multi-phase build.

- process_file(file_id): process/reprocess one file's gate-activity rows.
"""
from app.db.session import SessionLocal
from app.db.repositories.cms_gate_activity_detail_repository import CmsGateActivityDetailRepository
from app.db.repositories.gate_type_repository import GateTypeRepository
from app.db.repositories.process_log_error_repository import ProcessLogErrorRepository
from app.processing.gate_activity.mapper import map_row
from app.processing.gate_activity.writer import GateActivityWriter


class InvalidGateActivityError(Exception):
    """A file's mapped rows failed prevalidation; the file must not be processed."""


def process_file(file_id: int) -> int:
    """Map a file's staging rows into GateActivityDetail_tbl and return the row count.

    Upserts by identity, so re-running (or overlapping files in the rolling window) is
    idempotent: an existing row is updated in place, not duplicated. On any failure the
    whole file rolls back (nothing written) and the error is logged.
    """
    session = SessionLocal()
    try:
        rows = CmsGateActivityDetailRepository(session).get_by_file_id(file_id)
        mapped = [map_row(row) for row in rows]

        # Reject the whole file up front if any gate type is unknown. GateTypeId has no
        # FK in the DB, so this is the only guard against a bad value slipping through.
        _validate_gate_types(mapped, GateTypeRepository(session).id_set())

        GateActivityWriter(session).write_details(mapped)
        session.commit()
        return len(mapped)
    except Exception as exc:
        session.rollback()
        ProcessLogErrorRepository.write(
            f"Gate activity process failed for FileId {file_id}: {exc}"
        )
        raise
    finally:
        session.close()


def _validate_gate_types(mapped, valid_ids: set[int]) -> None:
    """Raise if any row names a GateTypeId the GateType lookup does not have."""
    unknown = sorted(
        {m.gate_type_id for m in mapped
         if m.gate_type_id is not None and m.gate_type_id not in valid_ids}
    )
    if unknown:
        raise InvalidGateActivityError(f"unknown GateTypeId(s): {unknown}")