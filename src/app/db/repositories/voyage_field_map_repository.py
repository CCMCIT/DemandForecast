"""Repository for VoyageFieldMap_tbl (per-voyage link table).

Mirrors VoyageDetailsRepository: add_all + delete_by_voyage_id, so reprocessing a
file deletes a voyage's existing maps and re-inserts the fresh set.
"""
from app.db.models.voyage_field_map import VoyageFieldMap


class VoyageFieldMapRepository:
    def __init__(self, session):
        self.session = session

    def add_all(self, maps: list[VoyageFieldMap]) -> None:
        self.session.add_all(maps)

    def delete_by_voyage_id(self, voyage_id: int) -> None:
        """Delete a voyage's field-map rows before re-inserting the current set."""
        self.session.query(VoyageFieldMap).filter(
            VoyageFieldMap.VoyageId == voyage_id
        ).delete(synchronize_session=False)