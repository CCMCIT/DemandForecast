"""Unit test (no DB): voyage prevalidation rejects rows missing VOYAGE or WORK_DATE."""
from datetime import date

import pytest

from app.processing.dto import MappedVoyage
from app.processing.validation import validate_voyages, InvalidFileError

pytestmark = pytest.mark.unit


def _voyage(voyage="FX123", work_date=date(2025, 7, 4)) -> MappedVoyage:
    return MappedVoyage(file_id=1, voyage=voyage, work_date=work_date, work_time=None)


def test_valid_voyages_pass():
    validate_voyages([_voyage(), _voyage(voyage="FX999")])  # no raise


def test_empty_list_passes():
    validate_voyages([])  # no rows -> nothing to reject


def test_blank_voyage_raises():
    with pytest.raises(InvalidFileError):
        validate_voyages([_voyage(voyage="   ")])


def test_none_voyage_raises():
    with pytest.raises(InvalidFileError):
        validate_voyages([_voyage(voyage=None)])


def test_missing_work_date_raises():
    with pytest.raises(InvalidFileError):
        validate_voyages([_voyage(work_date=None)])


def test_error_message_names_the_problem_voyage():
    with pytest.raises(InvalidFileError, match="FX123"):
        validate_voyages([_voyage(voyage="FX123", work_date=None)])


def test_one_bad_row_among_good_ones_still_raises():
    with pytest.raises(InvalidFileError):
        validate_voyages([_voyage(), _voyage(voyage=None), _voyage(voyage="FX999")])
