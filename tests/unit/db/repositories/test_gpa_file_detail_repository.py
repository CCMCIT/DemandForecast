"""Unit test (no DB): parsing the GPA REPORTED value into a datetime.

REPORTED arrives in two shapes, and the time must be KEPT, not dropped:
  - '07102026'      -> MMDDYYYY       -> 2026-07-10 00:00  (no time given -> midnight)
  - '071020261348'  -> MMDDYYYYHHMM   -> 2026-07-10 13:48  (time preserved)

Anything else must fail LOUDLY -- raise, not silently return None. This includes
a blank or missing value: a silent None disables the fallen-off classification
with no error logged, which is the bug this test guards against. A blank REPORTED
is a real data problem, so it must surface, not pass quietly.
"""
from datetime import datetime

import pytest

from app.db.repositories.gpa_file_detail_repository import _parse_reported

pytestmark = pytest.mark.unit


def test_date_with_time_keeps_the_time():
    # The real feed's MMDDYYYYHHMM form: the HHMM time must be preserved, not dropped.
    assert _parse_reported("071020261348") == datetime(2026, 7, 10, 13, 48)


def test_date_only_parses_to_midnight():
    # The MMDDYYYY form has no time -> midnight, but is still a datetime (one return type).
    assert _parse_reported("07102026") == datetime(2026, 7, 10, 0, 0)


def test_reported_is_stripped_before_parsing():
    assert _parse_reported("  071020261348  ") == datetime(2026, 7, 10, 13, 48)


@pytest.mark.parametrize("value", [None, "", "   ", "BADDATE"])
def test_unreadable_or_blank_reported_fails_loudly(value):
    # No datetime could be read -- INCLUDING a blank or missing value. This must NOT
    # pass silently (a silent None disables the fallen-off classification with no
    # error logged); it must raise so the problem is visible.
    with pytest.raises(ValueError):
        _parse_reported(value)


def test_loud_failure_names_the_offending_value():
    # "Clear": when a value is present but unreadable, the error names it.
    with pytest.raises(ValueError) as exc:
        _parse_reported("BADDATE")
    assert "BADDATE" in str(exc.value)
