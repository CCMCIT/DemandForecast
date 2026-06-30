"""Purpose: persist a MappedVoyage into the shared Voyage_tbl + VoyageDetails_tbl.

Source-agnostic and reused by every company (Open/Closed): it consumes the
MappedVoyage contract, never a company's raw model. It depends on repository
abstractions, not on the session's query API (Dependency Inversion), and does no
commits — the runner owns the transaction. Mode/Direction names are resolved via
lookup maps passed in once per run, so no per-row DB hits.
"""
from app.db.models.voyage import Voyage
from app.db.models.voyage_details import VoyageDetails
from app.db.repositories.voyage_repository import VoyageRepository
from app.db.repositories.voyage_details_repository import VoyageDetailsRepository
from app.processing.dto import MappedVoyage


class VoyageWriter:
    def __init__(self, session, mode_ids: dict[str, int], direction_ids: dict[str, int]):
        self.voyages = VoyageRepository(session)
        self.details = VoyageDetailsRepository(session)
        self.mode_ids = mode_ids
        self.direction_ids = direction_ids

    def write(self, mapped: MappedVoyage) -> None:
        voyage = self.voyages.add(
            Voyage(
                FileId=mapped.file_id,
                Voyage=mapped.voyage,
                WORK_DATE=mapped.work_date,
                WorkTime=mapped.work_time,
            )
        )  # flush -> VoyageId
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