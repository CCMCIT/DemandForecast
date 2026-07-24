"""Integration test: reprocessing a street-use-days row upserts it in place.

Processes two files carrying the SAME identity (both gate dates + the four dimension columns)
but different CountOfRecords. The second run must update the same StreetUseDaysDetail row --
keeping its StreetUseDaysDetailId, not inserting a duplicate -- and system-versioning must push
the previous version into StreetUseDaysDetailHistory_tbl.

Hits the live DB. The out-gate location is tagged with a random GUID so the identity is unique
per run and never collides; no cleanup is performed (rows are left behind on purpose).
"""
import datetime
import uuid

import pytest
from sqlalchemy import text

from app.lookups import FileType, LoadStatus
from app.db.session import SessionLocal
from app.db.models.load import Load
from app.db.models.cms_street_use_days_detail import CmsStreetUseDaysDetail
from app.db.models.street_use_days_detail import StreetUseDaysDetail
from app.processing.street_use_days import runner as sud_runner

pytestmark = pytest.mark.integration

OUT_GATE = datetime.datetime(2026, 5, 22, 8, 0)
IN_GATE = datetime.datetime(2026, 5, 28, 17, 30)


def _seed(file_name: str, og_location: str, count: int) -> int:
    """Insert a street-use-days Load (ready to process) + one staging row. Returns the LoadId.
    Only `count` varies between calls; every identity column is identical, so the two files
    map to the same StreetUseDaysDetail row."""
    session = SessionLocal()
    try:
        file = Load(
            SourceName=file_name,
            LoadTypeId=FileType.STREET_USE_DAYS,
            LoadStatusId=LoadStatus.INSERTED_INTO_FILE_DETAIL,
        )
        session.add(file)
        session.flush()  # assign LoadId
        session.add(
            CmsStreetUseDaysDetail(
                LoadId=file.LoadId,
                OutGateDate=OUT_GATE,
                OutGateLocation=og_location,   # tagged -> makes the identity unique per run
                InGateDate=IN_GATE,
                InGateLocation="ITEST IN LOCATION",
                EquipmentCode="ITEST EQUIP",
                UltimateUser="ITEST CARRIER",
                CountOfRecords=count,
            )
        )
        session.commit()
        return file.LoadId
    finally:
        session.close()


def _history_counts(session, detail_id: int) -> list[int]:
    rows = session.execute(
        text(
            "SELECT CountOfRecords FROM DemandForecast.StreetUseDaysDetailHistory_tbl "
            "WHERE StreetUseDaysDetailId = :id"
        ),
        {"id": detail_id},
    ).fetchall()
    return [r[0] for r in rows]


def test_reprocess_updates_the_row_in_place_and_archives_the_old_version():
    guid = uuid.uuid4().hex
    og_location = f"ITEST OUT LOCATION {guid}"

    # --- Load 1: CountOfRecords = 3 -> inserts the row ---
    file1 = _seed(f"sudtest_{guid}_1.csv", og_location, count=3)
    sud_runner.process_file(file1)

    session = SessionLocal()
    try:
        row = session.query(StreetUseDaysDetail).filter(
            StreetUseDaysDetail.LoadId == file1
        ).one()
        detail_id = row.StreetUseDaysDetailId
        og_location_id = row.FieldTypeValueOGLocationId
        assert row.CountOfRecords == 3

        # Load advanced to "done"; nothing archived yet.
        assert session.get(Load, file1).LoadStatusId == LoadStatus.INSERTED_INTO_VOYAGE_DETAIL
        assert _history_counts(session, detail_id) == []
    finally:
        session.close()

    # --- Load 2: same identity, CountOfRecords = 9 -> updates in place ---
    file2 = _seed(f"sudtest_{guid}_2.csv", og_location, count=9)
    sud_runner.process_file(file2)

    session = SessionLocal()
    try:
        # Exactly one live row for this identity -> updated, not duplicated.
        live = session.query(StreetUseDaysDetail).filter(
            StreetUseDaysDetail.FieldTypeValueOGLocationId == og_location_id
        ).all()
        assert len(live) == 1
        row = live[0]
        assert row.StreetUseDaysDetailId == detail_id  # same row, id kept
        assert row.LoadId == file2                      # payload updated
        assert row.CountOfRecords == 9

        # Old version (CountOfRecords = 3) archived to history.
        assert _history_counts(session, detail_id) == [3]
    finally:
        session.close()
