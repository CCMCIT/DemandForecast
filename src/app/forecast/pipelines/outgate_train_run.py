"""Out-gate models: train one linear regression per chassis length and register
each through the shared write surface.

Mirrors day_of_week_train_run.py. Everything downstream of the fit -
coefficient_frame / metric_frame / feature-id resolution / register_model /
to_trained_model - is train_run.py's logic reused as-is; only the design matrix
is built differently, because two of the three predictor blocks are not
measured quantities in actuals_tbl (see forecast/outgate_features.py).

Model, per length:
    outgate_transactions ~ day-of-week + month-of-year + imports over prior 4 days

Prerequisite (same fail-fast contract as train_run.py): every referenced feature
must already exist in features_tbl. Apply sql/04_seed_outgate_features.sql once
before the first run. The write surface has no feature-creation proc by design.

Run:  python -m pipelines.outgate_train_run --modified-by svc_forecast \\
          --start 2023-01-01 --end 2025-06-30
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging

from db.engine import engine
from db.reads import CHASSIS_LENGTHS, ReadGateway
from db.writes import WriteGateway
from forecast import outgate_features, training
from pipelines.train_run import TrainingResult

log = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 4

# How far ahead the scoring run is made. Voyage rows are read as they stood this
# many days before each target date, so the model trains on import forecasts of
# the same vintage it will be handed in production. None trains on current
# voyage values - faster, but it fits a relationship that will not hold at
# scoring time and reports an in-sample R^2 the live model cannot reproduce.
DEFAULT_AS_OF_LEAD_DAYS = 4


def model_name_for(equip_length: int) -> str:
    return f"outgates_{equip_length}ft"


def run_outgate_training(
    *,
    equip_length: int,
    start_date: dt.date,
    end_date: dt.date,
    modified_by: str,
    reads: ReadGateway,
    writes: WriteGateway,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    as_of_lead_days: int | None = DEFAULT_AS_OF_LEAD_DAYS,
    loaded_only: bool = True,
    model_name: str | None = None,
    activate: bool = False,
    retire_previous_active: bool = False,
    model_version: int | None = None,   # None => proc assigns the next version
    upsert_target_actuals: bool = True,
) -> TrainingResult:
    """Fit and register one chassis length. Returns a TrainingResult whose
    trained_model can feed a scoring run without a float round-trip."""
    name = model_name or model_name_for(equip_length)
    target_feature = outgate_features.target_feature_name(equip_length)

    # --- read phase -------------------------------------------------------
    outgates = reads.daily_outgates(start_date, end_date, equip_lengths=(equip_length,))
    imports = reads.import_window(
        start_date,
        end_date,
        lookback_days=lookback_days,
        as_of_lead_days=as_of_lead_days,
        loaded_only=loaded_only,
        equip_lengths=(equip_length,),
    )

    # --- compute phase (pure, in memory) ---------------------------------
    frame = outgate_features.daily_frame(
        outgates, imports, equip_length, lookback_days=lookback_days
    )
    design, target = outgate_features.build_design(
        frame, equip_length, lookback_days=lookback_days
    )
    res = training.fit_ols(design, target)
    log.info(
        "%s: fit complete R^2=%.4f adj=%.4f n=%d DW=%.2f.",
        name, res.rsquared, res.rsquared_adj, int(res.nobs),
        float(training.metric_frame(res)
              .set_index("metric_name")["metric_value"].get("durbin_watson", float("nan"))),
    )

    coefficients = training.coefficient_frame(res)   # includes the '(Intercept)' row
    metrics = training.metric_frame(res)

    # --- resolve feature ids; fail fast on anything unseeded --------------
    needed = [*coefficients["feature_name"], target_feature]
    id_df = reads.feature_ids(needed)
    feature_id_of = dict(zip(id_df.feature_name, id_df.feature_id))
    missing = [n for n in dict.fromkeys(needed) if n not in feature_id_of]
    if missing:
        raise ValueError(
            f"Features not registered in features_tbl: {missing}. "
            "Apply sql/04_seed_outgate_features.sql before training."
        )
    coefficients = coefficients.assign(
        feature_id=coefficients["feature_name"].map(feature_id_of)
    )

    # --- write phase ------------------------------------------------------
    # Ground truth first: the realized target is shared by every model of this
    # quantity and is what model_predictions joins predictions against.
    if upsert_target_actuals:
        actuals = frame[["observation_date", "outgate_transactions"]].rename(
            columns={"outgate_transactions": "actual_value"}
        )
        actuals.insert(0, "feature_id", int(feature_id_of[target_feature]))
        writes.upsert_actuals(actuals=actuals, modified_by=modified_by)

    outcome = writes.register_model(
        model_name=name,
        target_feature_id=int(feature_id_of[target_feature]),
        coefficients=coefficients[["feature_id", "coefficient_value", "std_error", "p_value"]],
        metrics=metrics,
        modified_by=modified_by,
        model_version=model_version,
        is_active=activate,
        retire_previous_active=retire_previous_active,
    )

    trained_model = training.to_trained_model(
        res, model_id=outcome["model_id"], feature_id_of=feature_id_of
    )
    log.info(
        "Registered %s v%d as model_id=%d.",
        name, outcome["model_version"], outcome["model_id"],
    )
    return TrainingResult(
        model_id=outcome["model_id"],
        model_version=outcome["model_version"],
        r_squared=float(res.rsquared),
        n_observations=int(res.nobs),
        trained_model=trained_model,
    )


def run_all_lengths(
    *,
    start_date: dt.date,
    end_date: dt.date,
    modified_by: str,
    reads: ReadGateway,
    writes: WriteGateway,
    equip_lengths=CHASSIS_LENGTHS,
    **kwargs,
) -> dict[int, TrainingResult]:
    """Train and register every length. Each length is its own atomic
    registration; a failure part-way leaves earlier lengths registered, which is
    recoverable (re-running assigns a new version) and preferable to holding a
    transaction open across three fits."""
    return {
        length: run_outgate_training(
            equip_length=length,
            start_date=start_date,
            end_date=end_date,
            modified_by=modified_by,
            reads=reads,
            writes=writes,
            **kwargs,
        )
        for length in equip_lengths
    }


# --- CLI --------------------------------------------------------------------
def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(
        description="Train and register the CCM out-gate models (one per chassis length)."
    )
    p.add_argument("--start", required=True, type=_parse_date, help="window start YYYY-MM-DD")
    p.add_argument("--end", required=True, type=_parse_date, help="window end YYYY-MM-DD")
    p.add_argument("--modified-by", required=True, help="acting user / service account")
    p.add_argument("--lengths", type=int, nargs="+", default=list(CHASSIS_LENGTHS))
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    p.add_argument(
        "--as-of-lead-days", type=int, default=DEFAULT_AS_OF_LEAD_DAYS,
        help="read voyage forecasts as they stood this many days before each target date",
    )
    p.add_argument(
        "--current-voyage-values", action="store_true",
        help="ignore --as-of-lead-days and train on latest voyage rows (exploration only)",
    )
    p.add_argument("--include-empties", action="store_true",
                   help="count empty import containers as well as loaded")
    p.add_argument("--activate", action="store_true")
    p.add_argument("--retire-previous-active", action="store_true")
    p.add_argument("--skip-actuals", action="store_true",
                   help="do not upsert the realized target into actuals_tbl")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run_all_lengths(
        start_date=args.start,
        end_date=args.end,
        modified_by=args.modified_by,
        reads=ReadGateway(engine),
        writes=WriteGateway(engine),
        equip_lengths=tuple(args.lengths),
        lookback_days=args.lookback_days,
        as_of_lead_days=None if args.current_voyage_values else args.as_of_lead_days,
        loaded_only=not args.include_empties,
        activate=args.activate,
        retire_previous_active=args.retire_previous_active,
        upsert_target_actuals=not args.skip_actuals,
    )
    for length, result in results.items():
        print(
            f"{model_name_for(length)}: model_id={result.model_id} "
            f"version={result.model_version} R^2={result.r_squared:.4f} "
            f"n={result.n_observations}"
        )


if __name__ == "__main__":
    main()
