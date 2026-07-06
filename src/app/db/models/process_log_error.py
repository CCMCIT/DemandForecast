"""Model for ADMIN.Process_Log_Error_tbl. Reflected from the live DB.

Shared team error-log table used by several unrelated apps in the same DB.
This project writes rows tagged ErrorProcedure = '##ForecastDemand##' so its
errors can be filtered out from the others.

Only the columns this app populates are set; the rest stay NULL by design
(Process_Log_Step_Id, UserName, ErrorNumber, ErrorState, ErrorSeverity,
ErrorLine). Column names/types match the live table.
"""
from datetime import datetime

from sqlalchemy import Integer
from sqlalchemy.dialects.mssql import DATETIME, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ProcessLogError(Base):
    __tablename__ = "Process_Log_Error_tbl"
    __table_args__ = {"schema": "ADMIN"}

    Process_Log_Error_Id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Process_Log_Step_Id: Mapped[int | None] = mapped_column(Integer)   # left NULL
    UserName: Mapped[str | None] = mapped_column(VARCHAR)              # left NULL
    ErrorNumber: Mapped[int | None] = mapped_column(Integer)          # left NULL
    ErrorState: Mapped[int | None] = mapped_column(Integer)           # left NULL
    ErrorSeverity: Mapped[int | None] = mapped_column(Integer)        # left NULL
    ErrorLine: Mapped[int | None] = mapped_column(Integer)            # left NULL
    ErrorProcedure: Mapped[str | None] = mapped_column(VARCHAR)       # '##ForecastDemand##'
    ErrorMessage: Mapped[str | None] = mapped_column(VARCHAR)         # str(exc)
    ErrorDateTime: Mapped[datetime | None] = mapped_column(DATETIME)  # nullable, no default -> set in code