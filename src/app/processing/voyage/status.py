"""Purpose: classify a voyage that has fallen off the report as Called or Cancelled.

Source-agnostic and DB-free: given the voyage's last work date and the reported
date of its last appearance, decide the status. The single business threshold
lives here as a constant so it is easy to change.

A voyage listed on the report right up to its work date arrived (Called); one
that dropped off while still more than THRESHOLD days before its work date never
came (Cancelled).
"""
from datetime import date, timedelta

from app.lookups import VoyageStatus

# "Called" if the planned work date is at most this many days after the last
# reported date; otherwise "Cancelled". Change here to adjust the rule.
CANCELLED_THRESHOLD_DAYS = 1


def classify(work_date: date, reported_date: date) -> VoyageStatus:
    if work_date <= reported_date + timedelta(days=CANCELLED_THRESHOLD_DAYS):
        return VoyageStatus.CALLED
    return VoyageStatus.CANCELED
