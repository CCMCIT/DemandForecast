"""Integration test: VoyageStatusId lifecycle (ToCall -> Called / Cancelled -> ToCall).

A voyage is "ToCall" while it is on the report. When it drops off (a later file no
longer contains it) it is classified from its OWN last appearance:

    W = the voyage's WORK_DATE            (planned arrival, on Voyage_tbl)
    R = the REPORTED date of its last file (MMDDYYYY, on GpaFileDetail_tbl)

    Called    when  W <= R + CANCELLED_THRESHOLD_DAYS   (listed ~until it arrived)
    Cancelled when  W >  R + CANCELLED_THRESHOLD_DAYS    (vanished while still ahead)

If it appears again on a later file it goes back to ToCall.

These tests hit the live DB. FileName and VOYAGE are tagged with a random GUID so
runs never collide; no cleanup is performed (rows are left behind on purpose).

Note: processing any file classifies every ToCall voyage that is absent from it,
so a run may touch unrelated ToCall rows in the shared DB. Each test only asserts
on its own GUID-tagged voyages, so that side effect never affects the results.
"""
import datetime
import uuid

import pytest

from app.lookups import FileType, LoadStatus, VoyageStatus
from app.db.session import SessionLocal
from app.db.models.file import File
from app.db.models.gpa_file_detail import GpaFileDetail
from app.db.models.voyage import Voyage
from app.processing.voyage import runner as processing_runner
from app.processing.voyage.status import CANCELLED_THRESHOLD_DAYS

pytestmark = pytest.mark.integration

WORK_DATE = datetime.date(2025, 7, 4)

# REPORTED is an MMDDYYYY string. Chosen relative to WORK_DATE (4 Jul) to sit right
# on either side of the threshold, so the tests exercise the exact boundary.
REPORTED_WITHIN_THRESHOLD = "07032025"   # 3 Jul: W - R = 1 day  -> Called
REPORTED_BEYOND_THRESHOLD = "07022025"   # 2 Jul: W - R = 2 days -> Cancelled


def _seed_file(file_name: str, voyage: str, reported: str) -> int:
    """Insert a File (ready to process) + one GpaFileDetail for `voyage`. Returns
    the FileId. WORK_DATE is fixed; REPORTED is what drives the classification."""
    session = SessionLocal()
    try:
        file = File(
            FileName=file_name,
            FileTypeId=FileType.GPA,
            LoadStatusId=LoadStatus.INSERTED_INTO_FILE_DETAIL,
        )
        session.add(file)
        session.flush()  # assign FileId
        session.add(
            GpaFileDetail(
                FileId=file.FileId,
                TERMINAL="ITEST",
                VESSEL="ITEST VESSEL",
                VOYAGE=voyage,
                WORK_DATE=WORK_DATE,
                WORKTIME=datetime.time(0, 0),
                REPORTED=reported,
                IM_FULL20=5,
            )
        )
        session.commit()
        return file.FileId
    finally:
        session.close()


def _drop_off_the_report(guid: str) -> None:
    """Process a file that does NOT contain the target voyage(s), so they fall off
    the report and get classified. The file carries its own unrelated voyage."""
    file_id = _seed_file(
        f"trigger_{guid}.csv", f"IT_{guid}_OTHER", REPORTED_WITHIN_THRESHOLD
    )
    processing_runner.process_file(file_id)


def _status_of(voyage_tag: str) -> int:
    session = SessionLocal()
    try:
        return session.query(Voyage).filter(Voyage.Voyage == voyage_tag).one().VoyageStatusId
    finally:
        session.close()


def test_threshold_is_one_day():
    """Guards the tests below: they assume the threshold is exactly 1 day."""
    assert CANCELLED_THRESHOLD_DAYS == 1


def test_new_voyage_starts_as_to_call():
    guid = uuid.uuid4().hex
    voyage = f"IT_{guid}"

    # Step 1: process a file containing the voyage.
    processing_runner.process_file(_seed_file(f"test_{guid}.csv", voyage, REPORTED_WITHIN_THRESHOLD))

    # Step 2: while on the report it is ToCall.
    assert _status_of(voyage) == VoyageStatus.TO_CALL


def test_voyage_is_called_when_last_report_is_within_threshold():
    guid = uuid.uuid4().hex
    voyage = f"IT_{guid}"

    # Step 1: voyage appears with REPORTED = 3 Jul, WORK_DATE = 4 Jul (1 day gap).
    processing_runner.process_file(_seed_file(f"test_{guid}.csv", voyage, REPORTED_WITHIN_THRESHOLD))
    assert _status_of(voyage) == VoyageStatus.TO_CALL

    # Step 2: a later file omits it -> it falls off the report.
    _drop_off_the_report(guid)

    # Step 3: gap is 1 day (<= threshold) -> it arrived -> Called.
    assert _status_of(voyage) == VoyageStatus.CALLED


def test_voyage_is_cancelled_when_last_report_is_beyond_threshold():
    guid = uuid.uuid4().hex
    voyage = f"IT_{guid}"

    # Step 1: voyage appears with REPORTED = 2 Jul, WORK_DATE = 4 Jul (2 day gap).
    processing_runner.process_file(_seed_file(f"test_{guid}.csv", voyage, REPORTED_BEYOND_THRESHOLD))
    assert _status_of(voyage) == VoyageStatus.TO_CALL

    # Step 2: a later file omits it -> it falls off the report.
    _drop_off_the_report(guid)

    # Step 3: gap is 2 days (> threshold) -> it never came -> Cancelled.
    assert _status_of(voyage) == VoyageStatus.CANCELED


def test_reappearing_voyage_resets_to_to_call():
    guid = uuid.uuid4().hex
    voyage = f"IT_{guid}"

    # Step 1: voyage appears, then falls off beyond the threshold -> Cancelled.
    processing_runner.process_file(_seed_file(f"test_{guid}_1.csv", voyage, REPORTED_BEYOND_THRESHOLD))
    _drop_off_the_report(guid)
    assert _status_of(voyage) == VoyageStatus.CANCELED

    # Step 2: the voyage shows up again on a new file.
    processing_runner.process_file(_seed_file(f"test_{guid}_2.csv", voyage, REPORTED_WITHIN_THRESHOLD))

    # Step 3: back on the report -> reset to ToCall.
    assert _status_of(voyage) == VoyageStatus.TO_CALL