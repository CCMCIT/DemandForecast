"""Integration test: reprocessing an out-of-service row upserts it in place.

Processes two files carrying the SAME identity (Date + the two dimension columns) but
different Units. The second run must update the same OutOfServiceUnitsDetail row -- keeping
its OutOfServiceUnitsDetailId, not inserting a duplicate -- and system-versioning must push
the previous version into OutOfServiceUnitsDetailHistory_tbl.

Hits the live DB. The location name is tagged with a random GUID so the identity is unique
per run and never collides; no cleanup is performed (rows are left behind on purpose).
"""
import datetime
import uuid

import pytest
from sqlalchemy import text

from app.lookups import FileType, LoadStatus
from app.db.session import SessionLocal
from app.db.models.load import Load
from app.db.models.cms_out_of_service_units_detail import CmsOutOfServiceUnitsDetail
from app.db.models.out_of_service_units_detail import OutOfServiceUnitsDetail
from app.processing.out_of_service import runner as oos_runner

pytestmark = pytest.mark.integration

DAY = datetime.date(2026, 5, 22)


def _seed(file_name: str, location: str, units: int) -> int:
    """Insert an out-of-service Load (ready to process) + one staging row. Returns the LoadId.
    Only `units` varies between calls; every identity column is identical, so the two files
    map to the same OutOfServiceUnitsDetail row."""
    session = SessionLocal()
    try:
        file = Load(
            SourceName=file_name,
            LoadTypeId=FileType.OUT_OF_SERVICE,
            LoadStatusId=LoadStatus.INSERTED_INTO_FILE_DETAIL,
        )
        session.add(file)
        session.flush()  # assign LoadId
        session.add(
            CmsOutOfServiceUnitsDetail(
                LoadId=file.LoadId,
                Date=DAY,
                EquipCode="ITEST EQUIP",
                LocationName=location,        # tagged -> makes the identity unique per run
                Units=units,
            )
        )
        session.commit()
        return file.LoadId
    finally:
        session.close()


def _history_units(session, detail_id: int) -> list[int]:
    rows = session.execute(
        text(
            "SELECT Units FROM DemandForecast.OutOfServiceUnitsDetailHistory_tbl "
            "WHERE OutOfServiceUnitsDetailId = :id"
        ),
        {"id": detail_id},
    ).fetchall()
    return [r[0] for r in rows]


def test_reprocess_updates_the_row_in_place_and_archives_the_old_version():
    guid = uuid.uuid4().hex
    location = f"ITEST LOCATION {guid}"

    # --- Load 1: Units = 3 -> inserts the row ---
    file1 = _seed(f"oostest_{guid}_1.csv", location, units=3)
    oos_runner.process_file(file1)

    session = SessionLocal()
    try:
        row = session.query(OutOfServiceUnitsDetail).filter(
            OutOfServiceUnitsDetail.LoadId == file1
        ).one()
        detail_id = row.OutOfServiceUnitsDetailId
        location_id = row.FieldTypeValueLocationId
        assert row.Units == 3

        # Load advanced to "done"; nothing archived yet.
        assert session.get(Load, file1).LoadStatusId == LoadStatus.INSERTED_INTO_VOYAGE_DETAIL
        assert _history_units(session, detail_id) == []
    finally:
        session.close()

    # --- Load 2: same identity, Units = 9 -> updates in place ---
    file2 = _seed(f"oostest_{guid}_2.csv", location, units=9)
    oos_runner.process_file(file2)

    session = SessionLocal()
    try:
        # Exactly one live row for this identity -> updated, not duplicated.
        live = session.query(OutOfServiceUnitsDetail).filter(
            OutOfServiceUnitsDetail.FieldTypeValueLocationId == location_id
        ).all()
        assert len(live) == 1
        row = live[0]
        assert row.OutOfServiceUnitsDetailId == detail_id  # same row, id kept
        assert row.LoadId == file2                          # payload updated
        assert row.Units == 9

        # Old version (Units = 3) archived to history.
        assert _history_units(session, detail_id) == [3]
    finally:
        session.close()