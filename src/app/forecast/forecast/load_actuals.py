"""Actuals loader - hand realized ground truth to the MERGE upsert proc.

Thin by design: actuals land and get corrected over time, and the insert-or-
update logic lives in usp_upsert_actuals, not here.
"""
from __future__ import annotations

import pandas as pd

from db.writes import WriteGateway


def load_actuals(
    *,
    actuals: pd.DataFrame,   # feature_id, observation_date, actual_value
    modified_by: str,
    writes: WriteGateway,
) -> None:
    writes.upsert_actuals(actuals=actuals, modified_by=modified_by)
