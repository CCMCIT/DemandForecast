"""Score a registered out-gate model forward over a horizon and store the run.

The model is LOADED from the database, not re-fitted. Everything the scoring
object needs is persisted: coefficients in model_coefficients_tbl, the full
(X'X)^-1 in model_covariance_tbl, and residual_std_error / residual_df as rows
in model_metrics_tbl. The training window and filters come from
model_parameters_tbl, so this takes --model-id and nothing else about the fit.

Why that matters beyond convenience: actuals_tbl is a MERGE upsert built for
backfill and correction, and the gate feed is reprocessed, so re-fitting "the
same window" is not a stable operation - months later it can produce different
coefficients from the same dates. A model reconstructed from stored rows scores
identically forever, whatever has changed underneath it since.

TWO GUARDS remain, because the failures they catch are silent:

  1. Import coverage. VoyageDetails is fed by the GPA nine-day vessel report, so
     forecast voyages run out roughly nine days ahead. Past that the import
     window has nothing to sum, and a missing row is indistinguishable from a
     genuine zero once it reaches the model - it would predict a quiet, biased
     drop rather than admit it does not know. Uncovered days are reported and,
     by default, dropped from the horizon.

  2. Unseen calendar levels. A month absent from training has no dummy in the
     model, so a target date in that month silently scores as the BASELINE
     month. Training on Feb-Jun and scoring into July is not a small
     extrapolation - it is July being priced as February. Refused by default.

Run:  python run_forecast.py outgate-score --env dev --model-id <id> \\
          --horizon-days 30 --modified-by <account>
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging

import pandas as pd

from app.config.settings import DEFAULT_ENV, Env
from db import engine as engine_module
from db.reads import ReadGateway
from db.writes import WriteGateway
from forecast import outgate_features
from forecast.score_run import run_scoring
from forecast.trained_model import TrainedModel

log = logging.getLogger(__name__)

DEFAULT_HORIZON_DAYS = 30
DEFAULT_CONFIDENCE = 0.95


# --- load the stored model --------------------------------------------------

def load_model(
    *, model_id: int, reads: ReadGateway
) -> tuple[TrainedModel, list[str], dict[str, int], dict[str, str]]:
    """Reconstruct the registered model from stored rows.

    Returns (model, predictor feature names, feature_name -> feature_id,
    training parameters). No re-fit, no source-data read, no training-window
    argument - the stored rows ARE the model.
    """
    definition = reads.model_definition(model_id)
    if not bool(definition["is_scoreable"]):
        expected = int(definition["coefficient_count"]) ** 2
        raise ValueError(
            f"model_id={model_id} ('{definition['model_name']}' "
            f"v{definition['model_version']}) is not scoreable: "
            f"{definition['coefficient_count']} coefficients and "
            f"{definition['covariance_cell_count']} covariance cells "
            f"(expected {expected}), or residual_std_error / residual_df are "
            "missing. Models registered before migration 05 carry no covariance "
            "and must be re-registered by re-running training."
        )

    model = reads.load_trained_model(model_id)
    parameters = reads.model_parameters(model_id)

    names = reads.feature_names(list(model.feature_order))
    name_of = dict(zip(names.feature_id.astype(int), names.feature_name))
    missing = [f for f in model.feature_order if f not in name_of]
    if missing:
        raise ValueError(f"feature_id(s) {missing} are not present in features_tbl.")

    # The intercept is excluded - the model injects it, and run_scoring does not
    # expect an input row for it.
    predictor_ids = [f for f in model.feature_order if f != model.intercept_feature_id]
    predictor_names = [name_of[f] for f in predictor_ids]
    feature_id_of = dict(zip(predictor_names, predictor_ids))

    log.info(
        "Loaded '%s' v%s (model_id=%d): %d predictors, trained on %s to %s.",
        definition["model_name"], definition["model_version"], model_id,
        len(predictor_names),
        parameters.get("train_start_date", "?"), parameters.get("train_end_date", "?"),
    )
    return model, predictor_names, feature_id_of, parameters


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

    Every predictor gets a row for every target date - the design vector needs
    all of them. Calendar dummies are deterministic (is_forecasted_value = 0);
    the import window is the port's own forecast, so it is flagged 1 throughout,
    which is what lets those rows be found later when analysing how forecast
    error propagates across the horizon.
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
                value, forecasted = float(import_by_date.get(target_date, 0.0)), 1
            elif name.startswith(f"{outgate_features.DOW_PREFIX}_"):
                value = 1.0 if name == f"{outgate_features.DOW_PREFIX}_{day_name}" else 0.0
                forecasted = 0
            elif name.startswith(f"{outgate_features.MONTH_PREFIX}_"):
                value = 1.0 if name == f"{outgate_features.MONTH_PREFIX}_{month_name}" else 0.0
                forecasted = 0
            else:
                raise ValueError(
                    f"Predictor '{name}' is neither a calendar dummy nor the import "
                    "window; this scorer does not know how to supply it."
                )
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
    """Months / weekdays in the horizon the model has no dummy for AND that are
    not its baseline - those score as the baseline level without saying so."""
    def check(prefix, levels_in_order, observed):
        retained = [n[len(prefix) + 1:] for n in predictor_names if n.startswith(prefix + "_")]
        if not retained:
            return []   # block absent from the model entirely; nothing to extrapolate
        first_idx = levels_in_order.index(retained[0])
        baseline = levels_in_order[first_idx - 1] if first_idx else None
        known = set(retained) | ({baseline} if baseline else set())
        return sorted({lvl for lvl in observed if lvl not in known})

    return {
        "month": check(outgate_features.MONTH_PREFIX, outgate_features.MONTH_ORDER,
                       {d.month_name() for d in target_dates}),
        "day_of_week": check(outgate_features.DOW_PREFIX, outgate_features.DOW_ORDER,
                             {d.day_name() for d in target_dates}),
    }


def _import_coverage(target_dates, imports) -> pd.DataFrame:
    """Per target date, whether its lookback window has any voyage data at all.
    A date without it is not 'zero imports' - it is unknown, and the model has no
    way to represent that."""
    covered = set(pd.to_datetime(imports["observation_date"]))
    return pd.DataFrame(
        {"target_date": target_dates, "has_window": [d in covered for d in target_dates]}
    )


# --- orchestration ----------------------------------------------------------

def run_outgate_scoring(
    *,
    model_id: int,
    reads: ReadGateway,
    writes: WriteGateway,
    modified_by: str,
    as_of_date: dt.date | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    confidence_level: float = DEFAULT_CONFIDENCE,
    allow_unseen_months: bool = False,
    allow_missing_imports: bool = False,
) -> dict:
    as_of_date = as_of_date or dt.date.today()

    model, predictor_names, feature_id_of, parameters = load_model(
        model_id=model_id, reads=reads
    )
    equip_length = int(parameters["equip_length"])
    lookback_days = int(parameters["lookback_days"])
    loaded_only = parameters["loaded_only"] == "1"
    imports_column = outgate_features.imports_feature_name(equip_length, lookback_days)

    target_dates = pd.date_range(
        as_of_date + dt.timedelta(days=1), periods=horizon_days, freq="D"
    )

    # Scoring always reads the LATEST voyage forecast. as_of_lead_days is a
    # training-time device for reproducing what was knowable in the past; at
    # scoring time the most recent forecast is simply the best available.
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
    if any(unseen.values()):
        message = (
            f"Horizon covers calendar levels absent from training: {unseen}. Those "
            "dates score as the model's BASELINE level, with nothing in the output "
            "to say so."
        )
        if not allow_unseen_months:
            raise ValueError(
                message + " Shorten the horizon, retrain on a window covering them, "
                "retrain without the month block, or pass --allow-unseen-months."
            )
        log.warning(message)

    # --- guard 2: import coverage ---
    coverage = _import_coverage(target_dates, imports)
    uncovered = coverage.loc[~coverage["has_window"], "target_date"]
    if len(uncovered):
        log.warning(
            "%d of %d horizon days have no voyage data for their %d-day import window "
            "(from %s). The GPA feed is a nine-day vessel report, so this is expected "
            "beyond roughly nine days out.",
            len(uncovered), len(target_dates), lookback_days, uncovered.min().date(),
        )
        if not allow_missing_imports:
            target_dates = pd.DatetimeIndex(coverage.loc[coverage["has_window"], "target_date"])
            if len(target_dates) == 0:
                raise ValueError(
                    "No horizon day has voyage coverage for its import window; scoring "
                    "would be calendar-only with imports pinned at zero."
                )
            log.warning(
                "Horizon truncated to %d covered day(s), through %s. Pass "
                "--allow-missing-imports to score the full horizon with uncovered "
                "windows treated as zero.",
                len(target_dates), target_dates.max().date(),
            )

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
        "equip_length": equip_length,
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
    p.add_argument(
        "--model-id", required=True, type=int,
        help="registered model to score; the training window and filters come "
             "from its stored parameters",
    )
    p.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--as-of", type=_parse_date, default=dt.date.today(),
                   help="run / data-cutoff date (default: today)")
    p.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE,
                   help="prediction-interval level, 0-1 (default: 0.95)")
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

    reads = ReadGateway(engine)
    result = run_outgate_scoring(
        model_id=args.model_id,
        reads=reads,
        writes=WriteGateway(engine),
        modified_by=args.modified_by,
        as_of_date=args.as_of,
        horizon_days=args.horizon_days,
        confidence_level=args.confidence,
        allow_unseen_months=args.allow_unseen_months,
        allow_missing_imports=args.allow_missing_imports,
    )

    # Read the run back out of the view - proves the round-trip.
    stored = reads.predictions_vs_actuals(args.model_id)
    stored = stored.loc[stored["input_batch_id"] == result["input_batch_id"]]
    print(f"\n=== [{env.value}] out-gate forecast (model_id={args.model_id}, "
          f"{result['equip_length']}ft, as_of={result['as_of_date'].isoformat()}) ===")
    if stored.empty:
        print("WARNING: no stored rows read back for this batch.")
        return
    for r in stored.sort_values("target_date").itertuples(index=False):
        band = ""
        if pd.notna(r.predicted_lower) and pd.notna(r.predicted_upper):
            band = f"  [{r.predicted_lower:,.0f} - {r.predicted_upper:,.0f}]"
        print(f"{r.target_date}  lead={r.lead_time_days:>3}d  {r.predicted_value:>8,.0f}{band}")
    negatives = int(stored["predicted_lower"].dropna().lt(0).sum())
    if negatives:
        print(f"\nNOTE: {negatives} lower bound(s) are negative. OLS does not know the "
              "target is a count; treat those as zero when staging.")
    print(f"\n[input_batch_id={result['input_batch_id']}, read back from "
          "DemandForecast.model_predictions]")


if __name__ == "__main__":
    main()
