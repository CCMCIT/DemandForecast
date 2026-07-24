"""Training orchestrator - the compute-then-commit boundary for a training run.

Mirrors score_run.py: all reads and all statistics happen first, in memory; only
then does the single atomic write go out (usp_register_model, via WriteGateway).
Feature resolution is part of the read phase, so an unknown feature fails the run
before any write.

This script is glue: no logic here is worth unit-testing on its own. It wires
reads (ReadGateway) + compute (forecast.training) to write (WriteGateway), and
returns the freshly built TrainedModel so a scoring run can follow without a
float round-trip through the DB.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
from dataclasses import dataclass

from app.config.settings import DEFAULT_ENV, Env
from db import engine as engine_module
from db.reads import ReadGateway
from db.writes import WriteGateway
from forecast import training
from forecast.trained_model import TrainedModel

log = logging.getLogger(__name__)


@dataclass(frozen=True, eq=False)  # eq=False: TrainedModel holds ndarrays
class TrainingResult:
    model_id: int
    model_version: int
    r_squared: float
    n_observations: int
    trained_model: TrainedModel   # ready to hand straight to a scoring run


def run_training(
    *,
    model_name: str,
    target_feature: str,
    predictors: list[str],
    start_date: dt.date,
    end_date: dt.date,
    modified_by: str,
    reads: ReadGateway,
    writes: WriteGateway,
    activate: bool = False,
    retire_previous_active: bool = False,
    min_observations: int = 20,
    model_version: int | None = None,   # None => proc assigns the next version
) -> TrainingResult:
    """Train one linear regression and register it. Returns a TrainingResult."""
    # --- read phase (includes fail-fast feature resolution) ---
    needed = [target_feature, *predictors, training.INTERCEPT_FEATURE_NAME]
    id_df = reads.feature_ids(needed)
    feature_id_of = dict(zip(id_df.feature_name, id_df.feature_id))
    missing = [n for n in dict.fromkeys(needed) if n not in feature_id_of]
    if missing:
        raise ValueError(
            f"Features not registered in features_tbl: {missing}. "
            "Register them (including '(Intercept)') before training."
        )

    long_actuals = reads.training_actuals(target_feature, predictors, start_date, end_date)

    # --- compute phase (pure, in memory) ---
    design, target = training.build_design_matrix(
        long_actuals, target_feature, predictors, min_observations=min_observations
    )
    res = training.fit_ols(design, target)
    log.info("Fit complete: R^2=%.4f, n=%d.", res.rsquared, int(res.nobs))

    coefficients = training.coefficient_frame(res)
    coefficients = coefficients.assign(
        feature_id=coefficients["feature_name"].map(feature_id_of)
    )
    metrics = training.metric_frame(res)

    # --- write phase (one atomic proc call) ---
    outcome = writes.register_model(
        model_name=model_name,
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
        model_name, outcome["model_version"], outcome["model_id"],
    )
    return TrainingResult(
        model_id=outcome["model_id"],
        model_version=outcome["model_version"],
        r_squared=float(res.rsquared),
        n_observations=int(res.nobs),
        trained_model=trained_model,
    )


# --- CLI (binds the engine to --env, then wires it to the gateways) ---------
def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(
        description="Train and register a linear regression model in DemandForecast."
    )
    p.add_argument(
        "--env",
        choices=[e.value for e in Env],
        default=DEFAULT_ENV.value,
        help="Database environment: dev, uat or prod (default: dev).",
    )
    p.add_argument("--model-name", required=True)
    p.add_argument("--target", required=True, help="target feature_name (must exist in features_tbl)")
    p.add_argument("--predictors", required=True, nargs="+", help="predictor feature_names")
    p.add_argument("--start", required=True, type=_parse_date, help="window start YYYY-MM-DD")
    p.add_argument("--end", required=True, type=_parse_date, help="window end YYYY-MM-DD")
    p.add_argument("--modified-by", required=True, help="acting user / service account")
    p.add_argument("--activate", action="store_true", help="mark the new version active")
    p.add_argument("--retire-previous-active", action="store_true",
                   help="when activating, retire prior active versions of this model_name")
    p.add_argument("--min-observations", type=int, default=20)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Bind the engine to the chosen environment before any DB work, exactly as
    # entrypoints/cli.py does with db_session.configure().
    env = Env(args.env)
    engine_module.configure(env)
    log.info("Target database environment: %s.", env.value)
    engine = engine_module.get_engine()

    result = run_training(
        model_name=args.model_name,
        target_feature=args.target,
        predictors=args.predictors,
        start_date=args.start,
        end_date=args.end,
        modified_by=args.modified_by,
        reads=ReadGateway(engine),
        writes=WriteGateway(engine),
        activate=args.activate,
        retire_previous_active=args.retire_previous_active,
        min_observations=args.min_observations,
    )
    print(
        f"[{env.value}] Registered model_id={result.model_id} "
        f"version={result.model_version} R^2={result.r_squared:.4f} "
        f"n={result.n_observations}"
    )


if __name__ == "__main__":
    main()
