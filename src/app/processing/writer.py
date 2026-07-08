"""Purpose: persist a MappedVoyage into the shared Voyage_tbl + VoyageDetails_tbl.

Source-agnostic and reused by every company (Open/Closed): it consumes the
MappedVoyage contract, never a company's raw model. It depends on repository
abstractions, not on the session's query API (Dependency Inversion), and does no
commits — the runner owns the transaction. Mode/Direction names are resolved via
lookup maps passed in once per run, so no per-row DB hits.
"""
from app.db.models.voyage import Voyage
from app.db.models.voyage_details import VoyageDetails
from app.db.models.voyage_field_map import VoyageFieldMap
from app.db.repositories.voyage_repository import VoyageRepository
from app.db.repositories.voyage_details_repository import VoyageDetailsRepository
from app.db.repositories.field_value_repository import FieldValueRepository
from app.db.repositories.field_type_value_repository import FieldTypeValueRepository
from app.db.repositories.voyage_field_map_repository import VoyageFieldMapRepository
from app.lookups import VoyageStatus
from app.processing.dto import MappedVoyage


class VoyageWriter:
    def __init__(self, session, mode_ids: dict[str, int], direction_ids: dict[str, int]):
        self.session = session
        self.voyages = VoyageRepository(session)
        self.details = VoyageDetailsRepository(session)
        # Shared dimension repos preload their caches once per file (one query each).
        self.field_values = FieldValueRepository(session)
        self.field_type_values = FieldTypeValueRepository(session)
        self.field_maps = VoyageFieldMapRepository(session)
        self.mode_ids = mode_ids
        self.direction_ids = direction_ids

    def write_voyage(self, mapped: MappedVoyage) -> Voyage:
        """Phase 1: insert or replace the voyage only, no details.

        Kept separate from write_details so the runner can commit all voyages
        first (LoadStatus 3) before any detail is written. Returns the persisted
        Voyage so the runner can pair it with its details in phase 2.
        """
        return self._replace_or_add_voyage(mapped)

    def write_details(self, mapped: MappedVoyage, voyage: Voyage) -> None:
        """Phase 2: insert the voyage's detail rows."""
        self.details.add_all(
            [
                VoyageDetails(
                    VoyageId=voyage.VoyageId,
                    FieldTypeValueEquipTypeId=d.field_type_value_id,
                    ModeId=self.mode_ids[d.mode_name],
                    DirectionId=self.direction_ids[d.direction_name],
                    ContainerLoadedFlag=bool(d.container_loaded_flag),
                    Containers=d.containers,
                )
                for d in mapped.details
            ]
        )

    def write_fields(self, mapped: MappedVoyage, voyage: Voyage) -> None:
        """Phase 2: (re)write the voyage's field maps.

        FieldValue and FieldTypeValue are shared dimension rows -- get-or-create,
        never deleted. VoyageFieldMap is per-voyage: delete-and-reinsert keyed by
        VoyageId (mirrors write_details), so reprocessing a file overwrites cleanly.
        """
        self.field_maps.delete_by_voyage_id(voyage.VoyageId)
        maps = []
        for f in mapped.fields:
            field_value_id = self.field_values.get_or_create_id(f.value)
            field_type_value_id = self.field_type_values.get_or_create_id(
                f.field_type_id, field_value_id
            )
            maps.append(
                VoyageFieldMap(
                    VoyageId=voyage.VoyageId,
                    FieldTypeValueId=field_type_value_id,
                )
            )
        self.field_maps.add_all(maps)

    def _replace_or_add_voyage(self, mapped: MappedVoyage) -> Voyage:
        """Insert the voyage, or replace it if it already exists.

        On replace, the UPDATE archives the previous voyage version to
        VoyageHistory_tbl and deleting its details archives them to
        VoyageDetailsHistory_tbl (SQL Server system-versioning). Fresh details
        are re-inserted by write(). This is what makes reprocessing a file
        overwrite-with-history instead of failing on the unique Voyage key.
        """
        existing = self.voyages.get_by_voyage(mapped.voyage)
        if existing is None:
            return self.voyages.add(
                Voyage(
                    FileId=mapped.file_id,
                    Voyage=mapped.voyage,
                    WORK_DATE=mapped.work_date,
                    WorkTime=mapped.work_time,
                    VoyageStatusId=VoyageStatus.TO_CALL,
                )
            )  # flush -> VoyageId

        # On the report again -> back to ToCall (resets a prior Called/Cancelled).
        existing.FileId = mapped.file_id
        existing.WORK_DATE = mapped.work_date
        existing.WorkTime = mapped.work_time
        existing.VoyageStatusId = VoyageStatus.TO_CALL
        self.details.delete_by_voyage_id(existing.VoyageId)
        self.session.flush()  # apply UPDATE + DELETE before re-inserting details
        return existing