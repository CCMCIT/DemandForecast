"""Repository for ADMIN.Process_Log_Error_tbl — shared team error log.

write() inserts one error row on its OWN session and commits immediately, so
the row survives the caller rolling back its own transaction (e.g. a failed
file load / voyage write). Every row is tagged ErrorProcedure='##ForecastDemand##'
to mark it as this application's.
"""
import sys
import traceback
from datetime import datetime

from app.db.models.process_log_error import ProcessLogError
from app.db.session import SessionLocal

# Identifies this app's rows in the shared table.
_ERROR_PROCEDURE = "##ForecastDemand##"


class ProcessLogErrorRepository:
    def __init__(self, session):
        self.session = session

    def add(self, row: ProcessLogError) -> ProcessLogError:
        self.session.add(row)
        self.session.flush()  # assign the identity PK
        return row

    @staticmethod
    def write(message: str) -> None:
        """Best-effort error log on its own session (survives a caller rollback).

        Unmentioned columns (Process_Log_Step_Id, UserName, ErrorNumber,
        ErrorState, ErrorSeverity, ErrorLine) are left NULL by design.
        ErrorDateTime is set here because the column has no DB default.

        Never raises: it runs from an except block, so a logging failure must
        not replace the original exception being handled.
        """
        try:
            session = SessionLocal()
            try:
                session.add(
                    ProcessLogError(
                        ErrorMessage=message,
                        ErrorProcedure=_ERROR_PROCEDURE,
                        ErrorDateTime=datetime.now(),
                    )
                )
                session.commit()
            finally:
                session.close()
        except Exception:
            # Logging is best-effort: never re-raise (that would replace the
            # caller's real exception). But don't fail silently either — surface
            # WHY the log write failed on stderr.
            print("WARNING: failed to write to Process_Log_Error_tbl:", file=sys.stderr)
            traceback.print_exc()
