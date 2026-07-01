"""Repository for AppLog_tbl. Shared, domain-neutral log sink.

Two ways to write, on purpose:
- add():   enlist the row in the caller's session/transaction. Use for logs
           that should live and die with the work (e.g. an INFO written inside
           a healthy transaction).
- write(): write on a fresh, independent session and commit immediately. Use
           for errors: the row must survive the caller rolling back its own
           transaction (e.g. a failed file load that resets LoadStatus).
"""
from app.db.models.app_log import AppLog
from app.db.session import SessionLocal


class AppLogRepository:
    def __init__(self, session):
        self.session = session

    def add(self, log: AppLog) -> AppLog:
        self.session.add(log)
        self.session.flush()  # assign the identity LogId
        return log

    @staticmethod
    def write(
        source: str,
        level: str,
        message: str,
        detail: str | None = None,
        reference_id: int | None = None,
    ) -> None:
        """Write one log row on its own session so it survives a caller rollback."""
        session = SessionLocal()
        try:
            session.add(
                AppLog(
                    Source=source,
                    Level=level,
                    Message=message,
                    Detail=detail,
                    ReferenceId=reference_id,
                )
            )
            session.commit()
        finally:
            session.close()