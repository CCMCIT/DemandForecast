"""Prevalidation of mapped voyages, run after mapping and before any DB write.

Source-agnostic: it checks the MappedVoyage contract, so every source reuses it.
If any voyage is unusable the whole file is rejected (raise) -- the runner's
existing error path then rolls back (nothing has been written yet), marks the file
ERROR, and logs it. Minimal by design: only the fields the pipeline cannot proceed
without. Descriptive fields (Vessel, Line, ...) stay optional; blanks are skipped
downstream, so they are not validated here.
"""
from app.processing.voyage.dto import MappedVoyage


class InvalidFileError(Exception):
    """A file's mapped rows failed prevalidation; the file must not be processed."""


def validate_voyages(mapped: list[MappedVoyage], equipment_names: set[str]) -> None:
    """Raise InvalidFileError if any voyage is missing a required field or names an
    equipment type the DB does not have.

    Required: VOYAGE (the unique key) and WORK_DATE.

    `equipment_names` is what the DB holds for FieldType.EQUIPMENT_TYPE. That set is
    closed (the types map to a fixed external list), so a name outside it is a bug in
    the mapper, not a new value to create — reject the file rather than write a
    detail row with the wrong equipment.
    """
    problems: list[str] = []
    for index, voyage in enumerate(mapped):
        if not voyage.voyage or not voyage.voyage.strip():
            problems.append(f"row {index}: blank VOYAGE")
        if voyage.work_date is None:
            problems.append(f"voyage {voyage.voyage or f'row {index}'}: missing WORK_DATE")
        for detail in voyage.details:
            if detail.equipment_name is not None and detail.equipment_name not in equipment_names:
                problems.append(
                    f"voyage {voyage.voyage or f'row {index}'}: "
                    f"unknown equipment type '{detail.equipment_name}'"
                )
    if problems:
        raise InvalidFileError("; ".join(problems))