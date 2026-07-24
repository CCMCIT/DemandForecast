"""Unit test (no DB): voyage prevalidation rejects rows missing VOYAGE, WORK_DATE,
or REPORTED, or naming an equipment type the DB does not have."""
from datetime import date, datetime

import pytest

from app.processing.voyage.dto import MappedDetail, MappedVoyage
from app.processing.voyage.validation import validate_voyages, InvalidFileError

pytestmark = pytest.mark.unit

# Stands in for what the DB holds for FieldType.EQUIPMENT_TYPE: a closed set.
EQUIPMENT = {"20CH", "40CH", "45CH"}


def _voyage(voyage="FX123", work_date=date(2025, 7, 4),
            reported=datetime(2025, 7, 3), details=None) -> MappedVoyage:
    return MappedVoyage(
        file_id=1,
        voyage=voyage,
        work_date=work_date,
        work_time=None,
        reported=reported,
        details=details or [],
    )


def _detail(equipment_name="20CH") -> MappedDetail:
    return MappedDetail(
        equipment_name=equipment_name,
        mode_name="Vessel",
        direction_name="Import",
        container_loaded_flag=1,
        containers=10,
    )


def test_valid_voyages_pass():
    validate_voyages([_voyage(), _voyage(voyage="FX999")], EQUIPMENT)  # no raise


def test_empty_list_passes():
    validate_voyages([], EQUIPMENT)  # no rows -> nothing to reject


def test_blank_voyage_raises():
    with pytest.raises(InvalidFileError):
        validate_voyages([_voyage(voyage="   ")], EQUIPMENT)


def test_none_voyage_raises():
    with pytest.raises(InvalidFileError):
        validate_voyages([_voyage(voyage=None)], EQUIPMENT)


def test_missing_work_date_raises():
    with pytest.raises(InvalidFileError):
        validate_voyages([_voyage(work_date=None)], EQUIPMENT)


def test_missing_reported_raises():
    with pytest.raises(InvalidFileError):
        validate_voyages([_voyage(reported=None)], EQUIPMENT)


def test_error_message_names_the_problem_voyage():
    with pytest.raises(InvalidFileError, match="FX123"):
        validate_voyages([_voyage(voyage="FX123", work_date=None)], EQUIPMENT)


def test_one_bad_row_among_good_ones_still_raises():
    with pytest.raises(InvalidFileError):
        validate_voyages(
            [_voyage(), _voyage(voyage=None), _voyage(voyage="FX999")], EQUIPMENT
        )


# --- equipment type: a closed set, so an unknown name is a mapping bug ---

def test_known_equipment_passes():
    voyage = _voyage(details=[_detail("20CH"), _detail("40CH"), _detail("45CH")])
    validate_voyages([voyage], EQUIPMENT)  # no raise


def test_absent_equipment_passes():
    # The empties (IM_MT / EX_MT) carry no equipment type at all.
    validate_voyages([_voyage(details=[_detail(None)])], EQUIPMENT)  # no raise


def test_unknown_equipment_raises_naming_the_value():
    with pytest.raises(InvalidFileError, match="53CH"):
        validate_voyages([_voyage(details=[_detail("53CH")])], EQUIPMENT)


def test_unknown_equipment_among_good_details_still_raises():
    voyage = _voyage(details=[_detail("20CH"), _detail("53CH"), _detail("40CH")])
    with pytest.raises(InvalidFileError, match="53CH"):
        validate_voyages([voyage], EQUIPMENT)


def test_equipment_match_is_exact():
    # The DB lookup is an exact string match, so casing/padding must not slip through
    # and silently resolve to nothing downstream.
    for name in ("20ch", " 20CH", "20CH "):
        with pytest.raises(InvalidFileError):
            validate_voyages([_voyage(details=[_detail(name)])], EQUIPMENT)


def test_error_message_names_the_voyage_carrying_the_bad_equipment():
    voyage = _voyage(voyage="FX999", details=[_detail("53CH")])
    with pytest.raises(InvalidFileError, match="FX999"):
        validate_voyages([voyage], EQUIPMENT)
