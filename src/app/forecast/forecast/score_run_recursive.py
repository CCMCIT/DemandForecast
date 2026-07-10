"""Recursive scoring orchestrator - for models whose input on day d+1 is their
own prediction from day d (forecast-on-forecast chaining).

The generic run_scoring assumes every input is known up front and scores days
independently; it cannot chain. This variant rolls the horizon forward one day
at a time: score day d, then feed that prediction in as the chained input for
day d+1.

Input channel - one frame, `supplied_inputs`, carries every value the CALLER
supplies (as opposed to values this model's roll-forward generates):
  - every exogenous feature (vessel counts, calendar terms, forecasts from
    another model) for every day; and
  - the chained feature for the FIRST day only - its seed. On day 1 the chained
    feature is just a known input (yesterday's realized ending value), so it
    belongs in the same channel as any other known input. On days 2..N the loop
    supplies it from the prior day's prediction, so it must NOT appear in
    supplied_inputs for those days.

Each input is written as its own row with its own is_forecasted_value:
  - the seed keeps whatever flag the caller gives it (0 if yesterday's ending is
    a realized actual, 1 if it is itself still a forecast);
  - the chained feature is is_forecasted=1 on every day after the seed;
  - an exogenous feature keeps the caller's flag (0 known, 1 forecast-elsewhere).

Still compute-then-commit: the entire roll-forward is pure in-memory work using
TrainedModel.predict; only after the whole horizon is built do we do the single
atomic score_run write. The chaining is an ORCHESTRATION concern - it never
pushes into the procs or the DB.

CAVEAT (statistical, not code): the interval stored on an is_forecasted day is a
one-step interval CONDITIONAL on the forecasted input - it treats that input as
if it were known and so understates the uncertainty that compounds across the
horizon. The is_forecasted_value flag is what lets you find and correct those
rows downstream.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd

from db.writes import WriteGateway
from forecast.trained_model import TrainedModel

# Long-format shape expected for supplied_inputs (and produced for the write):
_INPUT_COLUMNS = ["feature_id", "target_date", "feature_value", "is_forecasted_value"]


def _required_features(model: TrainedModel) -> set[int]:
    """Every feature the model needs supplied, i.e. all columns except the intercept."""
    return {f for f in model.feature_order if f != model.intercept_feature_id}


def run_scoring_recursive(
    *,
    model: TrainedModel,
    target_dates: Sequence[date],
    chained_feature_id: int,          # the input feature fed by the prior day's prediction
    supplied_inputs: pd.DataFrame,    # all caller-supplied inputs, long-format (_INPUT_COLUMNS)
    as_of_date: date,
    confidence_level: float,
    modified_by: str,
    writes: WriteGateway,
) -> int:
    """Roll a self-feeding model forward across target_dates, then commit once.

    supplied_inputs must contain the chained feature exactly once, on the first
    target_date (its seed), and every exogenous feature the model needs on every
    day. The chained feature must NOT appear for later days - those come from the
    roll-forward.
    """
    if chained_feature_id == model.intercept_feature_id:
        raise ValueError("chained_feature_id cannot be the intercept feature.")
    if len(target_dates) == 0:
        raise ValueError("target_dates is empty.")

    first_day = target_dates[0]
    supplied = supplied_inputs.copy()
    supplied["_d"] = pd.to_datetime(supplied["target_date"]).dt.date

    # Split the chained feature (which seeds the roll-forward) from the exogenous
    # inputs (which are merged per day).
    is_chained = supplied["feature_id"] == chained_feature_id
    chained_rows = supplied[is_chained]
    exo_by_date = {d: g for d, g in supplied[~is_chained].groupby("_d")}

    # The chained feature may be supplied ONLY as the day-1 seed.
    extra_days = set(chained_rows["_d"]) - {first_day}
    if extra_days:
        raise ValueError(
            f"chained feature {chained_feature_id} may only be supplied for the first "
            f"target_date ({first_day}); later days come from the roll-forward. "
            f"Got extra day(s): {sorted(extra_days)}"
        )
    seed = chained_rows[chained_rows["_d"] == first_day]
    if len(seed) != 1:
        raise ValueError(
            f"expected exactly one seed row for chained feature {chained_feature_id} "
            f"on {first_day}, got {len(seed)}."
        )
    seed_row = seed.iloc[0]

    required = _required_features(model)
    input_records: list[dict] = []
    prediction_records: list[dict] = []

    carry = seed_row.feature_value                       # day-1 chained value = the seed
    carry_is_forecast = bool(seed_row.is_forecasted_value)

    for target_date in target_dates:
        # Start the day's feature vector and input rows with the chained feature.
        features = {chained_feature_id: carry}
        day_rows = [{
            "feature_id": chained_feature_id,
            "target_date": target_date,
            "feature_value": carry,
            "is_forecasted_value": carry_is_forecast,
        }]

        # Add this day's exogenous features (each keeps its own is_forecasted flag).
        for r in exo_by_date.get(target_date, pd.DataFrame(columns=_INPUT_COLUMNS)).itertuples(index=False):
            features[int(r.feature_id)] = r.feature_value
            day_rows.append({
                "feature_id": int(r.feature_id),
                "target_date": target_date,
                "feature_value": r.feature_value,
                "is_forecasted_value": bool(r.is_forecasted_value),
            })

        # Fail early and clearly if the model needs a feature nobody supplied.
        missing = required - set(features)
        if missing:
            raise ValueError(f"{target_date}: missing input(s) for feature_id(s) {sorted(missing)}")

        point = model.predict(features)
        lower, upper = model.interval(features, confidence_level)

        input_records.extend(day_rows)
        prediction_records.append({
            "target_date": target_date,
            "predicted_value": point,
            "predicted_lower": lower,
            "predicted_upper": upper,
        })

        # roll forward: today's prediction becomes tomorrow's chained input
        carry = point
        carry_is_forecast = True

    return writes.score_run(
        model_id=model.model_id,
        as_of_date=as_of_date,
        interval_confidence_level=confidence_level,
        inputs=pd.DataFrame(input_records, columns=_INPUT_COLUMNS),
        predictions=pd.DataFrame(prediction_records),
        modified_by=modified_by,
    )
