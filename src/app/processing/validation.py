"""Prevalidation of mapped voyages, run after mapping and before any DB write.

Source-agnostic: it checks the MappedVoyage contract, so every source reuses it.
If any voyage is unusable the whole file is rejected (raise) -- the runner's
existing error path then rolls back (nothing has been written yet), marks the file
ERROR, and logs it. Minimal by design: only the fields the pipeline cannot proceed
without. Descriptive fields (Vessel, Line, ...) stay optional; blanks are skipped
downstream, so they are not validated here.
"""
from app.processing.dto import MappedVoyage


class InvalidFileError(Exception):
    """A file's mapped rows failed prevalidation; the file must not be processed."""


def validate_voyages(mapped: list[MappedVoyage]) -> None:
    """Raise InvalidFileError if any voyage is missing a required field.

    Required: VOYAGE (the unique key) and WORK_DATE.
    """
    problems: list[str] = []
    for index, voyage in enumerate(mapped):
        if not voyage.voyage or not voyage.voyage.strip():
            problems.append(f"row {index}: blank VOYAGE")
        if voyage.work_date is None:
            problems.append(f"voyage {voyage.voyage or f'row {index}'}: missing WORK_DATE")
    if problems:
        raise InvalidFileError("; ".join(problems))