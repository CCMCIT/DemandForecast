"""Score a registered out-gate model forward over a horizon and store the run.

Mirrors day_of_week_score_run.py. run_scoring needs a TrainedModel carrying
(X'X)^-1 for the prediction interval, which the DB intentionally does not store,
so the model is REBUILT by re-fitting the same training window in memory and
attaching the registered model_id. The fit is deterministic, so this reproduces
the stored model exactly - and rather than assume that, the rebuilt coefficients
are checked against the ones in model_coefficients_tbl before anything is
scored. A mismatch means the training window passed here is not the one the
model was registered from, and the run stops.

TWO GUARDS, both of which exist because the failure they catch is silent:

  1. Import coverage. VoyageDetails is fed by the GPA nine-day vessel report, so
     forecast voyages run out roughly nine days ahead. Past that the import
     window has nothing to sum, and a missing row is indistinguishable from a
     genuine zero once it reaches the model - it would predict a quiet, biased
     drop rather than admit it does not know. Days without a fully covered
     lookback window are reported, and by default the horizon is truncated to
     the covered ones.

  2. Unseen calendar levels. A month (or weekday) absent from training has no
     dummy in the model, so a target date in that month silently scores as the
     BASELINE month. Training on Feb-Jun and scoring into July is not a small
     extrapolation - it is July being priced as February. Refused by default.

Run:  python run_forecast.py outgate-score --env dev --model-id <id> \\
          --equip-length 20 --train-start 2026-02-01 --train-end 2026-06-30 \\
          --horizon-days 30 --modified-by <account>
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging

import numpy as np
import pandas as pd
import statsmodels.api as sm

from app.config.settings import DEFAULT_ENV, Env
from db import engine as engine_module
from db.reads import ReadGateway
from db.writes import WriteGateway
from forecast import outgate_features, training
from forecast.score_run import run_scoring
from forecast.trained_model import TrainedModel
from pipelines.outgate_train_run import (
    DEFAULT_AS_OF_LEAD_DAYS,
    DEFAULT_LOOKBACK_DAYS,
)

log = logging.getLogger(__name__)

DEFAULT_HORIZON_DAYS = 30
DEFAULT_CONFIDENCE = 0.95

# Coefficients are stored DECIMAL(18,8); a faithful rebuild lands well inside this.
_COEF_TOLERANCE = 1e-6


# --- rebuild the scoring object ---------------------------------------------

def rebuild_trained_model(
    *,
    model_id: int,
    equip_length: int,
    train_start: dt.date,
    train_end: dt.date,
    lookback_days: int,
    as_of_lead_days: int | None,
    loaded_only: bool,
    reads: ReadGateway,
) -> tuple[TrainedModel, list[str], dict[str, int]]:
    """Re-fit the registered model in memory. Returns (model, retained predictor
    names, feature_name -> feature_id), and raises if the rebuild does not match
    what is stored under model_id."""
    outgates = reads.daily_outgates(train_start, train_end, equip_lengths=(equip_length,))
    imports = reads.import_window(
        train_start,
        train_end,
        lookback_days=lookback_days,
        as_of_lead_days=as_of_lead_days,
        loaded_only=loaded_only,
        equip_lengths=(equip_length,),
    )
    frame = outgate_features.daily_frame(
        outgates, imports, equip_length, lookback_days=lookback_days
    )
    design, target = outgate_features.build_design(
        frame, equip_length, lookback_days=lookback_days
    )
    res = training.fit_ols(design, target)

    coefficients = training.coefficient_frame(res)
    target_feature = outgate_features.target_feature_name(equip_length)
    needed = [*coefficients["feature_name"], target_feature]
    id_df = reads.feature_ids(needed)
    feature_id_of = dict(zip(id_df.feature_name, id_df.feature_id))
    missing = [n for n in dict.fromkeys(needed) if n not in feature_id_of]
    if missing:
        raise ValueError(f"Features not registered in features_tbl: {missing}.")

    _verify_against_registry(
        model_id=model_id, rebuilt=coefficients, feature_id_of=feature_id_of, reads=reads
    )

    model = training.to_trained_model(res, model_id=model_id, feature_id_of=feature_id_of)
    return model, list(design.columns), feature_id_of


def _verify_against_registry(*, model_id, rebuilt, feature_id_of, reads) -> None:
    """The rebuild is only valid if it reproduces the registered coefficients.

    Nothing in the schema records which training window produced a model, so a
    caller can silently pass the wrong --train-start/--train-end and score with
    a DIFFERENT model than the one whose model_id lands on the predictions. This
    turns that into an error.
    """
    stored = reads.coefficients(model_id)
    if stored.empty:
        raise ValueError(f"model_id={model_id} has no coefficients in model_coefficients_tbl.")

    merged = (
        rebuilt.assign(feature_id=rebuilt["feature_name"].map(feature_id_of))
        .merge(stored, on="feature_id", how="outer", suffixes=("_rebuilt", "_stored"))
    )
    absent = merged["coefficient_value_rebuilt"].isna() | merged["coefficient_value"].isna()
    if absent.any():
        raise ValueError(
            f"Rebuilt fit does not have the same feature set as model_id={model_id}: "
            f"{merged.loc[absent, 'feature_name'].tolist()}. The training window passed "
            "here is almost certainly not the one the model was registered from."
        )

    delta = (
        merged["coefficient_value_rebuilt"].astype(float)
        - merged["coefficient_value"].astype(float)
    ).abs()
    worst = float(delta.max())
    if worst > _COEF_TOLERANCE:
        offender = merged.loc[delta.idxmax(), "feature_name"]
        raise ValueError(
            f"Rebuilt coefficients differ from model_id={model_id} (worst: {offender}, "
            f"|delta|={worst:.3e} > {_COEF_TOLERANCE:.0e}). Check --train-start / "
            "--train-end and the voyage-value mode match the registered run."
        )
    log.info("Rebuild matches model_id=%d (max |delta| = %.2e).", model_id, worst)


# --- assemble the horizon ---------------------------------------------------

def build_future_inputs(
    *,
    target_dates: pd.DatetimeIndex,
    predictor_names: list[str],
    imports: pd.DataFrame,          # observation_date, imports_prior_window
    imports_column: str,
    feature_id_of: dict[str, int],
) -> pd.DataFrame:
    """Long-format inputs: one row per (feature, target_date).

    Every retained predictor gets a row for every target date - the model's
    design vector requires all of them. Calendar dummies are deterministic
    (is_forecasted_value = 0); the import window is the port's forecast, so it
    is flagged 1 throughout, which is what lets you separate these rows later
    when analysing how forecast error propagates.

    The intercept is NOT emitted - the model injects it.
    """
    import_by_date = dict(
        zip(pd.to_datetime(imports["observation_date"]), imports["imports_prior_window"])
    )

    rows = []
    for target_date in target_dates:
        day_name = target_date.day_name()
        month_name = target_date.month_name()
        for name in predictor_names:
            if name == imports_column:
                value = float(import_by_date.get(target_date, 0.0))
                forecasted = 1
            elif name.startswith(f"{outgate_features.DOW_PREFIX}_"):
                value = 1.0 if name == f"{outgate_features.DOW_PREFIX}_{day_name}" else 0.0
                forecasted = 0
            elif name.startswith(f"{outgate_features.MONTH_PREFIX}_"):
                value = 1.0 if name == f"{outgate_features.MONTH_PREFIX}_{month_name}" else 0.0
                forecasted = 0
            else:
                raise ValueError(f"Unrecognized predictor '{name}'.")
            rows.append(
                {
                    "feature_id": int(feature_id_of[name]),
                    "target_date": target_date.date(),
                    "feature_value": value,
                    "is_forecasted_value": forecasted,
                }
            )
    return pd.DataFrame(rows)


def _unseen_calendar_levels(target_dates, predictor_names) -> dict[str, list[str]]:
    """Target-date months / weekdays the model has no dummy for AND that are not
    its baseline - those score as the baseline level without saying so."""
    def check(prefix, levels_in_order, observed_getter):
        retained = [n[len(prefix) + 1:] for n in predictor_names if n.startswith(prefix + "_")]
        if not retained:
            return []   # whole block absent from the model; nothing to extrapolate
        # The baseline is the observed level immediately preceding the first retained one.
        first_retained_idx = levels_in_order.index(retained[0])
        baseline = levels_in_order[first_retained_idx - 1] if first_retained_idx else None
        known = set(retained) | ({baseline} if baseline else set())
        return sorted({lvl for lvl in observed_getter() if lvl not in known})

    return {
        "month": check(outgate_features.MONTH_PREFIX, outgate_features.MONTH_ORDER,
                       lambda: {d.month_name() for d in target_dates}),
        "day_of_week": check(outgate_features.DOW_PREFIX, outgate_features.DOW_ORDER,
                             lambda: {d.day_name() for d in target_dates}),
    }


def _import_coverage(target_dates, imports, lookback_days) -> pd.DataFrame:
    """Per target date, how many of its lookback days have voyage data.

    A date with partial or no coverage is not 'zero imports' - it is unknown,
    and the model cannot represent that.
    """
    covered = set(pd.to_datetime(imports["observation_date"]))
    return pd.DataFrame(
        {
            "target_date": target_dates,
            "has_window": [d in covered for d in target_dates],
        }
    )


# --- orchestration ----------------------------------------------------------

def run_outgate_scoring(
    *,
    model_id: int,
    equip_length: int,
    train_start: dt.date,
    train_end: dt.date,
    reads: ReadGateway,
    writes: WriteGateway,
    modified_by: str,
    as_of_date: dt.date | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    confidence_level: float = DEFAULT_CONFIDENCE,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    as_of_lead_days: int | None = DEFAULT_AS_OF_LEAD_DAYS,
    loaded_only: bool = True,
    allow_unseen_months: bool = False,
    allow_missing_imports: bool = False,
) -> dict:
    as_of_date = as_of_date or dt.date.today()

    model, predictor_names, feature_id_of = rebuild_trained_model(
        model_id=model_id,
        equip_length=equip_length,
        train_start=train_start,
        train_end=train_end,
        lookback_days=lookback_days,
        as_of_lead_days=as_of_lead_days,
        loaded_only=loaded_only,
        reads=reads,
    )

    target_dates = pd.date_range(
        as_of_date + dt.timedelta(days=1), periods=horizon_days, freq="D"
    )
    imports_column = outgate_features.imports_feature_name(equip_length, lookback_days)

    # Scoring always reads the LATEST voyage forecast - as_of_lead_days is a
    # training-time device for reproducing what was knowable in the past.
    imports = reads.import_window(
        target_dates.min().date(),
        target_dates.max().date(),
        lookback_days=lookback_days,
        as_of_lead_days=None,
        loaded_only=loaded_only,
        equip_lengths=(equip_length,),
    )

    # --- guard 1: calendar extrapolation ---
    unseen = _unseen_calendar_levels(target_dates, predictor_names)
    if any(unseen.values()) and not allow_unseen_months:
        raise ValueError(
            f"Horizon covers calendar levels absent from training: {unseen}. Those dates "
            "would score as the model's BASELINE level without any indication in the "
            "output. Either shorten the horizon, retrain on a window that covers them, "
            "retrain without the month block, or pass --allow-unseen-months to accept it."
        )
    if any(unseen.values()):
        log.warning("Scoring unseen calendar levels as baseline: %s", unseen)

    # --- guard 2: import coverage ---
    coverage = _import_coverage(target_dates, imports, lookback_days)
    uncovered = coverage.loc[~coverage["has_window"], "target_date"]
    if len(uncovered):
        first = uncovered.min().date()
        log.warning(
            "%d of %d horizon days have no voyage data in their %d-day window "
            "(from %s). The GPA feed is a nine-day vessel report, so this is expected "
            "beyond roughly nine days out.",
            len(uncovered), len(target_dates), lookback_days, first,
        )
        if not allow_missing_imports:
            target_dates = pd.DatetimeIndex(coverage.loc[coverage["has_window"], "target_date"])
            if len(target_dates) == 0:
                raise ValueError(
                    "No horizon day has voyage coverage for its import window. Scoring "
                    "would be calendar-only with imports pinned at zero."
                )
            log.warning("Horizon truncated to %d covered days (to %s). Pass "
                        "--allow-missing-imports to score the full horizon with "
                        "imports treated as zero.",
                        len(target_dates), target_dates.max().date())

    inputs = build_future_inputs(
        target_dates=target_dates,
        predictor_names=predictor_names,
        imports=imports,
        imports_column=imports_column,
        feature_id_of=feature_id_of,
    )

    input_batch_id = run_scoring(
        model=model,
        inputs=inputs,
        as_of_date=as_of_date,
        confidence_level=confidence_level,
        modified_by=modified_by,
        writes=writes,
    )
    log.info("Stored input_batch_id=%d for model_id=%d.", input_batch_id, model_id)
    return {
        "input_batch_id": input_batch_id,
        "model_id": model_id,
        "as_of_date": as_of_date,
        "target_dates": target_dates,
    }


# --- CLI (binds the engine to --env, then wires it to the gateways) ---------
def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(
        description="Score a registered out-gate model over a future horizon."
    )
    p.add_argument(
        "--env", choices=[e.value for e in Env], default=DEFAULT_ENV.value,
        help="Database environment: dev, uat or prod (default: dev).",
    )
    p.add_argument("--model-id", required=True, type=int, help="registered model to score under")
    p.add_argument("--equip-length", required=True, type=int, choices=[20, 40, 45])
    p.add_argument("--train-start", required=True, type=_parse_date,
                   help="training window start - MUST match the registered run")
    p.add_argument("--train-end", required=True, type=_parse_date,
                   help="training window end - MUST match the registered run")
    p.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--as-of", type=_parse_date, default=dt.date.today(),
                   help="run / data-cutoff date (default: today)")
    p.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE,
                   help="prediction-interval level (0-1)")
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    p.add_argument("--as-of-lead-days", type=int, default=DEFAULT_AS_OF_LEAD_DAYS,
                   help="training-time voyage vintage; must match the registered run")
    p.add_argument("--current-voyage-values", action="store_true",
                   help="the model was trained with --current-voyage-values")
    p.add_argument("--include-empties", action="store_true",
                   help="the model was trained with --include-empties")
    p.add_argument("--allow-unseen-months", action="store_true",
                   help="score months absent from training as the baseline month")
    p.add_argument("--allow-missing-imports", action="store_true",
                   help="score the full horizon, treating uncovered import windows as zero")
    p.add_argument("--modified-by", required=True, help="acting user / service account")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    env = Env(args.env)
    engine_module.configure(env)
    log.info("Target database environment: %s.", env.value)
    engine = engine_module.get_engine()

    result = run_outgate_scoring(
        model_id=args.model_id,
        equip_length=args.equip_length,
        train_start=args.train_start,
        train_end=args.train_end,
        reads=ReadGateway(engine),
        writes=WriteGateway(engine),
        modified_by=args.modified_by,
        as_of_date=args.as_of,
        horizon_days=args.horizon_days,
        confidence_level=args.confidence,
        lookback_days=args.lookback_days,
        as_of_lead_days=None if args.current_voyage_values else args.as_of_lead_days,
        loaded_only=not args.include_empties,
        allow_unseen_months=args.allow_unseen_months,
        allow_missing_imports=args.allow_missing_imports,
    )

    # Read the stored run back out of the view - proves the round-trip.
    reads = ReadGateway(engine)
    stored = reads.predictions_vs_actuals(args.model_id)
    stored = stored.loc[stored["input_batch_id"] == result["input_batch_id"]]
    print(f"\n=== [{env.value}] out-gate forecast "
          f"(model_id={args.model_id}, {args.equip_length}ft, "
          f"as_of={result['as_of_date'].isoformat()}) ===")
    if stored.empty:
        print("WARNING: no stored rows read back for this batch.")
        return
    for r in stored.sort_values("target_date").itertuples(index=False):
        band = ""
        if pd.notna(r.predicted_lower) and pd.notna(r.predicted_upper):
            band = f"  [{r.predicted_lower:,.0f} - {r.predicted_upper:,.0f}]"
        print(f"{r.target_date}  lead={r.lead_time_days:>3}d  "
              f"{r.predicted_value:>8,.0f}{band}")
    negatives = stored["predicted_lower"].dropna().lt(0).sum()
    if negatives:
        print(f"\nNOTE: {negatives} lower bound(s) are negative. OLS does not know the "
              "target is a count; treat those as zero when staging.")
    print(f"\n[input_batch_id={result['input_batch_id']}, "
          f"stored and read back from DemandForecast.model_predictions]")


if __name__ == "__main__":
    main()
