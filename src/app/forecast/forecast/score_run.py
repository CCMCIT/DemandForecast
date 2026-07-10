"""Scoring orchestrator - the compute-then-commit boundary.

All reads and all statistics happen first, in memory; only then does the single
atomic write go out. Because we score with coefficients we already hold (the
TrainedModel), nothing forces a DB read in the middle of the write phase, so the
run never straddles a transaction.

This script is glue: no logic here is worth unit-testing on its own. It wires
compute (TrainedModel) to write (WriteGateway).
"""
from __future__ import annotations

import pandas as pd

from db.writes import WriteGateway
from forecast.trained_model import TrainedModel


def run_scoring(
    *,
    model: TrainedModel,
    inputs: pd.DataFrame,       # feature_id, target_date, feature_value, is_forecasted_value
    as_of_date,
    confidence_level: float,
    modified_by: str,
    writes: WriteGateway,
) -> int:
    """Score every horizon day carried in `inputs`, then commit once.

    `inputs` is the already-assembled feature set (from reads + any upstream
    forecasts, with is_forecasted_value set accordingly). The intercept is NOT
    expected here - the model injects it. Returns the new input_batch_id.
    """
    predictions = []
    for target_date, group in inputs.groupby("target_date"):
        features = dict(zip(group.feature_id, group.feature_value))
        point = model.predict(features)
        lower, upper = model.interval(features, confidence_level)
        predictions.append((target_date, point, lower, upper))

    predictions_df = pd.DataFrame(
        predictions,
        columns=["target_date", "predicted_value", "predicted_lower", "predicted_upper"],
    )

    return writes.score_run(
        model_id=model.model_id,
        as_of_date=as_of_date,
        interval_confidence_level=confidence_level,
        inputs=inputs,
        predictions=predictions_df,
        modified_by=modified_by,
    )
