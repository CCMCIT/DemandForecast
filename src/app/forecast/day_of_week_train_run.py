"""Day-of-week model: train from the GPA gate-transactions extract and register
it in DemandForecast, reusing the same write surface as pipelines/train_run.py.

This is the productionized sibling of day_of_week_model.py. That script fits the
model (gate transactions ~ day-of-week) with sklearn and prints the result; this
one fits the SAME model with statsmodels - the library the rest of forecast/
standardizes on, and the only one that yields the standard errors, p-values, and
in-sample diagnostics that model_coefficients_tbl / model_metrics_tbl store -
then commits it through WriteGateway.register_model (one atomic usp_register_model
call).

Why not reuse pipelines.train_run.run_training directly: that orchestrator sources
its design matrix from actuals_tbl (reads.training_actuals). The day-of-week
predictors are calendar-derived dummies, not measured quantities in actuals_tbl,
so the design matrix is built here from the file instead. Everything downstream of
the fit - coefficient_frame / metric_frame / feature-id resolution / register_model
- is identical to train_run.py and reused as-is.

Prerequisite (same fail-fast contract as train_run.py): every feature this model
references must already exist in features_tbl - '(Intercept)', the target (default
'gate_transactions_daily'), and one row per RETAINED day-of-week dummy (e.g.
'day_of_week_Monday'). The dropped baseline weekday lives in the intercept and
needs no predictor row. The write surface has no feature-creation proc by design;
seed those rows before the first run.
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from db.engine import engine
from db.reads import ReadGateway
from db.writes import WriteGateway
from forecast import training
from pipelines.train_run import TrainingResult

log = logging.getLogger(__name__)

# day_of_week_model.py reads this same local extract. Overridable on the CLI.
DEFAULT_EXCEL = r"C:\Users\bkuhn\Downloads\GPA Gate Transactions by Day.xlsx"


# --- compute: file -> (design, target) -------------------------------------
def build_day_of_week_design(
    df: pd.DataFrame,
    *,
    date_column: str = "Date",
    records_column: str = "Records",
) -> tuple[pd.DataFrame, pd.Series]:
    """Excel rows -> (design, target) for the same fit day_of_week_model.py makes.

    One-hot the weekday with the first (alphabetical) level dropped - identical to
    the original OneHotEncoder(drop="first"). The dropped day is the baseline
    folded into the intercept. fit_ols adds the '(Intercept)' constant, so the
    design must NOT carry one itself. Columns are named 'day_of_week_<Day>' to
    match the feature_name rows in features_tbl.
    """
    frame = df[[date_column, records_column]].dropna()
    weekday = pd.to_datetime(frame[date_column]).dt.day_name()
    design = pd.get_dummies(weekday, prefix="day_of_week", drop_first=True).astype(float)
    target = frame[records_column].astype(float)
    return design, target


# --- orchestration: compute-then-commit ------------------------------------
def run_day_of_week_training(
    *,
    excel_path: str = DEFAULT_EXCEL,
    date_column: str = "Date",
    records_column: str = "Records",
    model_name: str = "day_of_week",
    target_feature: str = "gate_transactions_daily",
    modified_by: str,
    reads: ReadGateway,
    writes: WriteGateway,
    activate: bool = False,
    retire_previous_active: bool = False,
    model_version: int | None = None,   # None => proc assigns the next version
) -> TrainingResult:
    """Fit the day-of-week model and register it. Returns a TrainingResult whose
    trained_model can feed a scoring run without a float round-trip through the DB.
    """
    # --- read + compute the fit (pure, in memory) ---
    df = pd.read_excel(excel_path, parse_dates=[date_column])
    design, target = build_day_of_week_design(
        df, date_column=date_column, records_column=records_column
    )
    res = training.fit_ols(design, target)
    log.info("Fit complete: R^2=%.4f, n=%d.", res.rsquared, int(res.nobs))

    coefficients = training.coefficient_frame(res)   # includes the '(Intercept)' row
    metrics = training.metric_frame(res)

    # --- resolve feature ids; fail fast on anything unseeded (mirror train_run) ---
    needed = [*coefficients["feature_name"], target_feature]
    id_df = reads.feature_ids(needed)
    feature_id_of = dict(zip(id_df.feature_name, id_df.feature_id))
    missing = [n for n in dict.fromkeys(needed) if n not in feature_id_of]
    if missing:
        raise ValueError(
            f"Features not registered in features_tbl: {missing}. "
            "Seed them (including '(Intercept)') before training."
        )
    coefficients = coefficients.assign(
        feature_id=coefficients["feature_name"].map(feature_id_of)
    )

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


# --- CLI (wires the shared engine to the gateways) --------------------------
def main(argv=None) -> None:
    p = argparse.ArgumentParser(
        description="Train the day-of-week model and register it in DemandForecast."
    )
    p.add_argument("--excel", default=DEFAULT_EXCEL, help="path to the gate-transactions extract")
    p.add_argument("--date-column", default="Date")
    p.add_argument("--records-column", default="Records")
    p.add_argument("--model-name", default="day_of_week")
    p.add_argument("--target", default="gate_transactions_daily",
                   help="target feature_name (must exist in features_tbl)")
    p.add_argument("--modified-by", required=True, help="acting user / service account")
    p.add_argument("--activate", action="store_true", help="mark the new version active")
    p.add_argument("--retire-previous-active", action="store_true",
                   help="when activating, retire prior active versions of this model_name")
    p.add_argument("--model-version", type=int, default=None,
                   help="explicit version; omit to let the proc assign the next one")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    result = run_day_of_week_training(
        excel_path=args.excel,
        date_column=args.date_column,
        records_column=args.records_column,
        model_name=args.model_name,
        target_feature=args.target,
        modified_by=args.modified_by,
        reads=ReadGateway(engine),
        writes=WriteGateway(engine),
        activate=args.activate,
        retire_previous_active=args.retire_previous_active,
        model_version=args.model_version,
    )
    print(
        f"Registered model_id={result.model_id} version={result.model_version} "
        f"R^2={result.r_squared:.4f} n={result.n_observations}"
    )


if __name__ == "__main__":
    main()
