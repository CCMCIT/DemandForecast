"""Integration smoke test: insert a File row and a linked GpaFileDetail row.

Hits the live DB (see documentation/running_tests.md), so a working .env
connection is required. Everything runs in one transaction that is rolled
back at teardown, so no rows are left behind.
"""
import datetime
import uuid

import pytest

from app.db.session import SessionLocal
from app.db.models.file import File
from app.db.models.gpa_file_detail import GpaFileDetail

pytestmark = pytest.mark.integration


@pytest.fixture
def session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


# Inserts a File row plus a linked GpaFileDetail row, flushing so the DB assigns
# the identity PKs and applies the File server defaults, then reads the detail
# back. The whole thing runs in one transaction the fixture rolls back, so no
# rows are ever persisted.
def test_insert_file_and_gpa_detail(session):
    file = File(FileName="smoke_test.csv", FileType="GPA")
    session.add(file)
    session.flush()          # INSERT now so the identity FileId is assigned
    session.refresh(file)    # pull server defaults back from the DB

    assert file.FileId is not None
    assert file.DateLoaded is not None   # getdate() default applied
    assert file.LoadStatus is False      # BIT default 0

    detail = GpaFileDetail(
        FileId=file.FileId,
        TERMINAL="T1",
        WORK_DATE=datetime.date(2026, 6, 29),
        VESSEL="UnitTestVESSEL X",
        VOYAGE="V001",
        WORKTIME=datetime.time(8, 30),
        IM_FULL20=5,
        TOTAL=5,
        REPORTED=True,
    )
    session.add(detail)
    session.flush()

    assert detail.FileDetailId is not None

    got = session.get(GpaFileDetail, detail.FileDetailId)
    assert got.FileId == file.FileId
    assert got.VESSEL == "UnitTestVESSEL X"
    assert got.IM_FULL20 == 5


@pytest.fixture
def created_rows():
    """Collect primary keys a test creates, then hard-delete exactly those rows.

    Children (GpaFileDetail) are deleted before parents (File) to respect the FK.
    Runs even if the test fails partway, so the live DB is never left dirty.
    """
    file_ids = []
    detail_ids = []
    yield file_ids, detail_ids
    if not file_ids and not detail_ids:
        return
    s = SessionLocal()
    try:
        if detail_ids:
            s.query(GpaFileDetail).filter(
                GpaFileDetail.FileDetailId.in_(detail_ids)
            ).delete(synchronize_session=False)
        if file_ids:
            s.query(File).filter(File.FileId.in_(file_ids)).delete(
                synchronize_session=False
            )
        s.commit()
    finally:
        s.close()


# Commits a File row plus a linked GpaFileDetail row (FileName tagged with a
# GUID), then re-reads them from a separate session to prove they truly
# persisted across connections. The captured PKs are hard-deleted in teardown,
# so the live DB is left clean.
def test_commit_then_verify_in_separate_session(created_rows):
    file_ids, detail_ids = created_rows
    guid = str(uuid.uuid4())

    # Write and commit (separate session from the verification below).
    writer = SessionLocal()
    try:
        file = File(FileName=guid, FileType="GPA")
        writer.add(file)
        writer.commit()
        writer.refresh(file)
        file_ids.append(file.FileId)  # capture the real PK for cleanup

        detail = GpaFileDetail(
            FileId=file.FileId,
            TERMINAL="T1",
            WORK_DATE=datetime.date(2026, 6, 29),
            VESSEL="UnitTestVESSEL X",
            VOYAGE="V001",
            IM_FULL20=5,
            TOTAL=5,
            REPORTED=True,
        )
        writer.add(detail)
        writer.commit()
        writer.refresh(detail)
        detail_ids.append(detail.FileDetailId)  # capture the real PK for cleanup
    finally:
        writer.close()

    # Verify from a fresh session: proves the rows truly persisted, not just
    # that they were visible inside the writing transaction.
    reader = SessionLocal()
    try:
        got_file = reader.get(File, file_ids[0])
        assert got_file is not None
        assert got_file.FileType == "GPA"

        details = (
            reader.query(GpaFileDetail)
            .filter(GpaFileDetail.FileId == got_file.FileId)
            .all()
        )
        assert len(details) == 1
        assert details[0].VESSEL == "UnitTestVESSEL X"
        assert details[0].IM_FULL20 == 5
    finally:
        reader.close()
