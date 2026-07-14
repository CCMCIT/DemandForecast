"""Purpose: persist a MappedVoyage into the shared Voyage_tbl + VoyageDetails_tbl.

Source-agnostic and reused by every company (Open/Closed): it consumes the
MappedVoyage contract, never a company's raw model. It depends on repository
abstractions, not on the session's query API (Dependency Inversion), and does no
commits — the runner owns the transaction. Equipment/Mode/Direction names are
resolved via lookup maps passed in once per run, so no per-row DB hits.

The voyage's descriptive fields are written by the DB proc
DemandForecast.VoyageFieldMap_upsert (see write_fields).
"""
from sqlalchemy import text

from app.db.models.voyage import Voyage
from app.db.models.voyage_details import VoyageDetails
from app.db.repositories.voyage_repository import VoyageRepository
from app.db.repositories.voyage_details_repository import VoyageDetailsRepository
from app.lookups import VoyageStatus
from app.processing.dto import MappedVoyage


class VoyageWriter:
    def __init__(
        self,
        session,
        mode_ids: dict[str, int],
        direction_ids: dict[str, int],
        equipment_ids: dict[str, int],
    ):
        self.session = session
        self.voyages = VoyageRepository(session)
        self.details = VoyageDetailsRepository(session)
        self.mode_ids = mode_ids
        self.direction_ids = direction_ids
        self.equipment_ids = equipment_ids

    def write_voyage(self, mapped: MappedVoyage) -> Voyage:
        """Phase 1: insert or replace the voyage only, no details.

        Kept separate from write_details so the runner can commit all voyages
        first (LoadStatus 3) before any detail is written. Returns the persisted
        Voyage so the runner can pair it with its details in phase 2.
        """
        return self._replace_or_add_voyage(mapped)

    def load_voyages(self, mapped: list[MappedVoyage]) -> list[Voyage]:
        """Resume helper: return the already-saved Voyage for each mapped voyage,
        in the same order as `mapped`. Used when phase 1 is skipped because the
        voyages were committed by an earlier (interrupted) run."""
        by_number = self.voyages.get_by_voyage_numbers([m.voyage for m in mapped])
        return [by_number[m.voyage] for m in mapped]

    def write_details(self, mapped: MappedVoyage, voyage: Voyage) -> None:
        """Phase 2: insert the voyage's detail rows."""
        self.details.add_all(
            [
                VoyageDetails(
                    VoyageId=voyage.VoyageId,
                    FieldTypeValueEquipTypeId=self._equipment_id(d.equipment_name),
                    ModeId=self.mode_ids[d.mode_name],
                    DirectionId=self.direction_ids[d.direction_name],
                    ContainerLoadedFlag=bool(d.container_loaded_flag),
                    Containers=d.containers,
                )
                for d in mapped.details
            ]
        )

    def _equipment_id(self, name: str | None) -> int | None:
        """Resolve an equipment name to its FieldTypeValueId. Equipment types are a
        closed set owned by the DB, so an unknown name is a mapping bug, never a
        value to create. Prevalidation rejects the file first; this is the backstop."""
        if name is None:
            return None  # the empties (MT) carry no equipment type
        return self.equipment_ids[name]

    def write_fields(self, mapped: MappedVoyage, voyage: Voyage) -> None:
        """Phase 2: write the voyage's descriptive fields via the DB proc.

        DemandForecast.VoyageFieldMap_upsert owns the whole per-attribute unit:
        find-or-create FieldValue, find-or-create FieldTypeValue (inheriting the
        type's ExternalNotifFlag, ExternalId left NULL), then upsert the single
        map row for (voyage, field type). Called once per field on the runner's
        session, so it rides the same phase-2 transaction.
        """
        for f in mapped.fields:
            self.session.execute(
                text(
                    "EXEC DemandForecast.VoyageFieldMap_upsert "
                    ":voyage_id, :field_type_id, :field_value"
                ),
                {
                    "voyage_id": voyage.VoyageId,
                    "field_type_id": f.field_type_id,
                    "field_value": f.value,
                },
            )

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
