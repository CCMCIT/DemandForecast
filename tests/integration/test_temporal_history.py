"""Integration test: system-versioning moves the old voyage into history.

Processes two files that share the same VOYAGE but differ by one container count.
The second run must overwrite Voyage_tbl / VoyageDetails_tbl with the newest data
and push the previous version into VoyageHistory_tbl / VoyageDetailsHistory_tbl.

Hits the live DB. SourceName and VOYAGE are tagged with a random GUID so runs never
collide; no cleanup is performed (rows are left behind on purpose).
"""
import datetime
import uuid

import pytest
from sqlalchemy import text

from app.lookups import FileType, LoadStatus
from app.db.session import SessionLocal
from app.db.models.load import Load
from app.db.models.gpa_file_detail import GpaFileDetail
from app.db.models.voyage import Voyage
from app.db.models.voyage_details import VoyageDetails
from app.processing.voyage import runner as processing_runner

pytestmark = pytest.mark.integration

# _seed populates only IM_FULL20; the mapper skips NULL columns, so exactly one
# VoyageDetails row is produced per voyage.
EXPECTED_DETAILS = 1


def _seed(file_name: str, voyage: str, im_full20: int) -> int:
    """Insert a Load (ready to process) + one GpaFileDetail. Returns the LoadId.

    Only IM_FULL20 is populated, so after processing exactly one VoyageDetails row
    has a non-null Containers value — the one we vary between the two files.
    """
    session = SessionLocal()
    try:
        file = Load(
            SourceName=file_name,
            LoadTypeId=FileType.GPA,
            LoadStatusId=LoadStatus.INSERTED_INTO_FILE_DETAIL,
        )
        session.add(file)
        session.flush()  # assign LoadId
        session.add(
            GpaFileDetail(
                LoadId=file.LoadId,
                TERMINAL="ITEST",
                VESSEL="ITEST VESSEL",
                VOYAGE=voyage,
                WORK_DATE=datetime.date(2026, 5, 22),
                WORKTIME=datetime.time(0, 0),
                IM_FULL20=im_full20,
            )
        )
        session.commit()
        return file.LoadId
    finally:
        session.close()


def _history_voyage_file_ids(session, voyage: str) -> list[int]:
    rows = session.execute(
        text("SELECT LoadId FROM DemandForecast.VoyageHistory_tbl WHERE Voyage = :v"),
        {"v": voyage},
    ).fetchall()
    return [r[0] for r in rows]


def _history_detail_containers(session, voyage_id: int) -> list[int | None]:
    rows = session.execute(
        text(
            "SELECT Containers FROM DemandForecast.VoyageDetailsHistory_tbl "
            "WHERE VoyageId = :vid"
        ),
        {"vid": voyage_id},
    ).fetchall()
    return [r[0] for r in rows]


def test_reprocess_moves_old_voyage_and_details_to_history():
    guid = uuid.uuid4().hex
    voyage_tag = f"IT_{guid}"

    # --- Load 1: IM_FULL20 = 5 -> creates the voyage + details ---
    file1 = _seed(f"test_{guid}_1.csv", voyage_tag, im_full20=5)
    processing_runner.process_file(file1)

    session = SessionLocal()
    try:
        voyage = session.query(Voyage).filter(Voyage.Voyage == voyage_tag).one()
        voyage_id = voyage.VoyageId
        assert voyage.LoadId == file1

        details = session.query(VoyageDetails).filter(VoyageDetails.VoyageId == voyage_id).all()
        assert len(details) == EXPECTED_DETAILS
        loaded = [d for d in details if d.Containers is not None]
        assert len(loaded) == 1 and loaded[0].Containers == 5

        # Nothing archived yet.
        assert _history_voyage_file_ids(session, voyage_tag) == []
        assert _history_detail_containers(session, voyage_id) == []
    finally:
        session.close()

    # --- Load 2: same voyage, IM_FULL20 = 10 -> replaces, archiving the old ---
    file2 = _seed(f"test_{guid}_2.csv", voyage_tag, im_full20=10)
    processing_runner.process_file(file2)

    session = SessionLocal()
    try:
        # Newest kept in the base tables (same row, updated in place).
        voyage = session.query(Voyage).filter(Voyage.Voyage == voyage_tag).one()
        assert voyage.VoyageId == voyage_id
        assert voyage.LoadId == file2

        details = session.query(VoyageDetails).filter(VoyageDetails.VoyageId == voyage_id).all()
        assert len(details) == EXPECTED_DETAILS
        loaded = [d for d in details if d.Containers is not None]
        assert len(loaded) == 1 and loaded[0].Containers == 10

        # Old version moved to history: one archived voyage (from file1)...
        assert _history_voyage_file_ids(session, voyage_tag) == [file1]

        # ...and its full set of details, the varied one holding the old value 5.
        archived = _history_detail_containers(session, voyage_id)
        assert len(archived) == EXPECTED_DETAILS
        assert [c for c in archived if c is not None] == [5]
    finally:
        session.close()
