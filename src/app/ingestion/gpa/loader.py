"""GPA loader: raw rows -> GpaFileDetail_tbl. DB access via the repository only."""
from datetime import datetime

from app.ingestion.base import BaseLoader
from app.db.models.gpa_file_detail import GpaFileDetail
from app.db.repositories.gpa_file_detail_repository import GpaFileDetailRepository


class GpaLoader(BaseLoader):
    def load(self, session, file_id: int, rows: list[dict]) -> None:
        repo = GpaFileDetailRepository(session)
        repo.add_all([self._to_model(file_id, row) for row in rows])

    def _to_model(self, file_id: int, row: dict) -> GpaFileDetail:
        return GpaFileDetail(
            FileId=file_id,
            TERMINAL=self._text(row.get("TERMINAL")),
            WORK_DATE=self._date(row.get("WORK_DATE")),
            VESSEL=self._text(row.get("VESSEL")),
            VOYAGE=self._text(row.get("VOYAGE")),
            LINE=self._text(row.get("LINE")),
            SERVICE=self._text(row.get("SERVICE")),
            FROM_PORT=self._text(row.get("FROM_PORT")),
            TO_PORT=self._text(row.get("TO_PORT")),
            WORKTIME=self._time(row.get("WORKTIME")),
            IM_FULL20=self._int(row.get("IM_FULL20")),
            IM_FULL40=self._int(row.get("IM_FULL40")),
            IM_FULL45=self._int(row.get("IM_FULL45")),
            IM_MT=self._int(row.get("IM_MT")),
            EX_FULL20=self._int(row.get("EX_FULL20")),
            EX_FULL40=self._int(row.get("EX_FULL40")),
            EX_MT=self._int(row.get("EX_MT")),
            TOTAL=self._int(row.get("TOTAL")),
            RAIL_IM20=self._int(row.get("RAIL_IM20")),
            RAIL_IM40=self._int(row.get("RAIL_IM40")),
            REPORTED=self._text(row.get("REPORTED")),
        )

    @staticmethod
    def _text(value):
        return value or None

    @staticmethod
    def _int(value):
        return int(value) if value not in (None, "") else None

    @staticmethod
    def _date(value):
        # WORK_DATE arrives as YYYYMMDD, e.g. 20250918.
        return datetime.strptime(value, "%Y%m%d").date() if value else None

    @staticmethod
    def _time(value):
        # WORKTIME arrives as HHMM, e.g. 1700. Blank in current files.
        return datetime.strptime(value, "%H%M").time() if value else None