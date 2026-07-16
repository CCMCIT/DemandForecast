"""Integration test: reprocessing a gate-activity row upserts it in place.

Processes two files carrying the SAME identity (Date + the nine dimension columns) but
different measures. The second run must update the same GateActivityDetail row -- keeping
its GateActivityDetailId, not inserting a duplicate -- and system-versioning must push the
previous version into GateActivityDetailHistory_tbl.

Hits the live DB. The trucker name is tagged with a random GUID so the identity is unique
per run and never collides; no cleanup is performed (rows are left behind on purpose).
"""
import datetime
import uuid

import pytest
from sqlalchemy import text

from app.lookups import FileType, LoadStatus
from app.db.session import SessionLocal
from app.db.models.file import File
from app.db.models.cms_gate_activity_detail import CmsGateActivityDetail
from app.db.models.gate_activity_detail import GateActivityDetail
from app.processing.gate_activity import runner as gate_runner

pytestmark = pytest.mark.integration

DAY = datetime.date(2026, 5, 22)


def _seed(file_name: str, trucker: str, units: int, transactions: int) -> int:
    """Insert a gate-activity File (ready to process) + one staging row. Returns the
    FileId. Only `units`/`transactions` vary between calls; every identity column is
    identical, so the two files map to the same GateActivityDetail row."""
    session = SessionLocal()
    try:
        file = File(
            FileName=file_name,
            FileTypeId=FileType.GATE_ACTIVITIES,
            LoadStatusId=LoadStatus.INSERTED_INTO_FILE_DETAIL,
        )
        session.add(file)
        session.flush()  # assign FileId
        session.add(
            CmsGateActivityDetail(
                FileId=file.FileId,
                Date=DAY,
                TruckerName=trucker,          # tagged -> makes the identity unique per run
                EquipCode="ITEST EQUIP",
                EquipLength=40,
                LengthMatchId=1,
                OceanCarrierName="ITEST CARRIER",
                GateType="1",
                BareChassisFlag=False,
                ContainerLoadedFlag=True,
                LocationName="ITEST LOCATION",
                Units=units,
                Transactions=transactions,
            )
        )
        session.commit()
        return file.FileId
    finally:
        session.close()


def _history_units(session, detail_id: int) -> list[int]:
    rows = session.execute(
        text(
            "SELECT Units FROM DemandForecast.GateActivityDetailHistory_tbl "
            "WHERE GateActivityDetailId = :id"
        ),
        {"id": detail_id},
    ).fetchall()
    return [r[0] for r in rows]


def test_reprocess_updates_the_row_in_place_and_archives_the_old_version():
    guid = uuid.uuid4().hex
    trucker = f"ITEST TRUCKER {guid}"

    # --- File 1: Units = 3 -> inserts the row ---
    file1 = _seed(f"gatetest_{guid}_1.csv", trucker, units=3, transactions=2)
    gate_runner.process_file(file1)

    session = SessionLocal()
    try:
        row = session.query(GateActivityDetail).filter(
            GateActivityDetail.FileId == file1
        ).one()
        detail_id = row.GateActivityDetailId
        trucker_id = row.FieldTypeValueTruckerId
        assert (row.Units, row.Transactions) == (3, 2)

        # File advanced to "done"; nothing archived yet.
        assert session.get(File, file1).LoadStatusId == LoadStatus.INSERTED_INTO_VOYAGE_DETAIL
        assert _history_units(session, detail_id) == []
    finally:
        session.close()

    # --- File 2: same identity, Units = 9 -> updates in place ---
    file2 = _seed(f"gatetest_{guid}_2.csv", trucker, units=9, transactions=8)
    gate_runner.process_file(file2)

    session = SessionLocal()
    try:
        # Exactly one live row for this identity -> updated, not duplicated.
        live = session.query(GateActivityDetail).filter(
            GateActivityDetail.FieldTypeValueTruckerId == trucker_id
        ).all()
        assert len(live) == 1
        row = live[0]
        assert row.GateActivityDetailId == detail_id       # same row, id kept
        assert row.FileId == file2                          # payload updated
        assert (row.Units, row.Transactions) == (9, 8)

        # Old version (Units = 3) archived to history.
        assert _history_units(session, detail_id) == [3]
    finally:
        session.close()