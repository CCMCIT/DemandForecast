"""Purpose: orchestrate one file's processing into Voyage_tbl + VoyageDetails_tbl.

Shared flow, agnostic to the source: the detail repository and mapper are chosen
by the File's FileType via the registry, so this code is identical for every
company (Open/Closed). It owns the single transaction (commit all or roll back)
and stays free of any GPA-specific knowledge. Triggered by thin entrypoints; it
does not know how it was invoked.
"""
from app.db.session import SessionLocal
from app.db.repositories.file_repository import FileRepository
from app.db.repositories.mode_repository import ModeRepository
from app.db.repositories.direction_repository import DirectionRepository
from app.processing.registry import get_processor
from app.processing.writer import VoyageWriter


def process_file(file_id: int) -> int:
    session = SessionLocal()
    try:
        file = FileRepository(session).get(file_id)
        if file is None:
            raise ValueError(f"No File with FileId {file_id}")

        detail_repo_cls, map_row = get_processor(file.FileType)
        details = detail_repo_cls(session).get_by_file_id(file_id)

        writer = VoyageWriter(
            session,
            ModeRepository(session).name_to_id(),
            DirectionRepository(session).name_to_id(),
        )
        for detail in details:
            writer.write(map_row(detail))

        session.commit()
        return len(details)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()