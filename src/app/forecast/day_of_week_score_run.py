"""Score the day-of-week model one day into the future and store the run.

Trivial by construction: with day-of-week as the only predictor, every future
Tuesday scores like every past Tuesday. The point is to exercise the SCORING
path end to end - assemble inputs, predict a point + interval, land a batch with
its inputs and prediction via usp_score_run - and to prove the round-trip by
reading the stored row back out of the model_predictions view.

It scores under an EXISTING registered model_id (from a prior register run), so
no new model version is created. run_scoring needs a TrainedModel that carries
(X'X)^-1 for the prediction interval, which the DB intentionally does not store
(reads.py: carry the TrainedModel from training, don't rebuild coefficients from
DB floats). We reproduce that TrainedModel by re-fitting the SAME Excel data in
memory - the fit is deterministic, so the coefficients match the stored model
exactly - and attach the existing model_id to it. The re-fit is the sanctioned
way to obtain the scoring object; the registry row remains the model of record.
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
from forecast import training
from forecast.score_run import run_scoring
from day_of_week_train_run import DEFAULT_EXCEL, build_day_of_week_design

log = logging.getLogger(__name__)


def build_future_day_inputs(
    target_date: dt.date,
    predictor_names: list[str],       # the fit's day-of-week dummy columns
    feature_id_of: dict[str, int],
) -> pd.DataFrame:
    """One input row per predictor dummy for the target date: 1.0 for the
    matching weekday, 0.0 for the rest. is_forecasted_value=False - the weekday
    is known exactly, not itself a forecast. The intercept is NOT included here;
    the model injects it. If the target weekday is the dropped baseline, every
    dummy is 0.0 and the intercept alone carries the prediction.
    """
    active = f"day_of_week_{pd.Timestamp(target_date).day_name()}"
    return pd.DataFrame(
        {
            "feature_id": [feature_id_of[n] for n in predictor_names],
            "target_date": [target_date] * len(predictor_names),
            "feature_value": [1.0 if n == active else 0.0 for n in predictor_names],
            "is_forecasted_value": [False] * len(predictor_names),
        }
    )


def run_day_of_week_scoring(
    *,
    model_id: int,
    excel_path: str = DEFAULT_EXCEL,
    date_column: str = "Date",
    records_column: str = "Records",
    as_of_date: dt.date,
    confidence_level: float = 0.95,
    modified_by: str,
    reads: ReadGateway,
    writes: WriteGateway,
) -> dict:
    """Score as_of_date + 1 day under an existing model_id; return the stored row."""
    # --- rebuild the TrainedModel in memory (deterministic re-fit) ---
    df = pd.read_excel(excel_path, parse_dates=[date_column])
    design, target = build_day_of_week_design(
        df, date_column=date_column, records_column=records_column
    )
    res = training.fit_ols(design, target)

    predictor_names = list(design.columns)
    needed = [training.INTERCEPT_FEATURE_NAME, *predictor_names]
    id_df = reads.feature_ids(needed)
    feature_id_of = dict(zip(id_df.feature_name, id_df.feature_id))
    missing = [n for n in dict.fromkeys(needed) if n not in feature_id_of]
    if missing:
        raise ValueError(f"Features not registered in features_tbl: {missing}.")

    model = training.to_trained_model(res, model_id=model_id, feature_id_of=feature_id_of)

    # --- one day into the future ---
    target_date = as_of_date + dt.timedelta(days=1)
    inputs = build_future_day_inputs(target_date, predictor_names, feature_id_of)

    input_batch_id = run_scoring(
        model=model,
        inputs=inputs,
        as_of_date=as_of_date,
        confidence_level=confidence_level,
        modified_by=modified_by,
        writes=writes,
    )
    log.info("Scored %s under model_id=%d as input_batch_id=%d.",
             target_date.isoformat(), model_id, input_batch_id)

    # --- read the stored row back to prove the round-trip ---
    stored = reads.predictions_vs_actuals(model_id)
    stored = stored[stored["input_batch_id"] == input_batch_id]
    return {"input_batch_id": input_batch_id, "target_date": target_date, "stored": stored}


# --- CLI --------------------------------------------------------------------
def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(
        description="Score the day-of-week model one day ahead and store the run."
    )
    p.add_argument(
        "--env",
        choices=[e.value for e in Env],
        default=DEFAULT_ENV.value,
        help="Database environment: dev, uat or prod (default: dev).",
    )
    p.add_argument("--model-id", required=True, type=int,
                   help="existing registered model_id to score under (from a register run)")
    p.add_argument("--excel", default=DEFAULT_EXCEL, help="path to the gate-transactions extract")
    p.add_argument("--date-column", default="Date")
    p.add_argument("--records-column", default="Records")
    p.add_argument("--as-of", type=_parse_date, default=dt.date.today(),
                   help="data-cutoff date YYYY-MM-DD; the run forecasts as-of + 1 day (default: today)")
    p.add_argument("--confidence", type=float, default=0.95, help="prediction-interval level (0-1)")
    p.add_argument("--modified-by", required=True, help="acting user / service account")
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

    result = run_day_of_week_scoring(
        model_id=args.model_id,
        excel_path=args.excel,
        date_column=args.date_column,
        records_column=args.records_column,
        as_of_date=args.as_of,
        confidence_level=args.confidence,
        modified_by=args.modified_by,
        reads=ReadGateway(engine),
        writes=WriteGateway(engine),
    )

    stored = result["stored"]
    print(f"\n=== Day-of-week scoring run (env={env.value}, model_id={args.model_id}) ===")
    print(f"as_of={args.as_of.isoformat()}  target_date={result['target_date'].isoformat()} "
          f"({pd.Timestamp(result['target_date']).day_name()})  "
          f"input_batch_id={result['input_batch_id']}")
    if stored.empty:
        print("WARNING: no stored row read back for this batch.")
        return
    r = stored.iloc[0]
    band = ""
    if pd.notna(r.predicted_lower) and pd.notna(r.predicted_upper):
        lvl = f"{r.interval_confidence_level:.0%}" if pd.notna(r.interval_confidence_level) else "n/a"
        band = f"   interval[{lvl}]: [{r.predicted_lower:,.1f}, {r.predicted_upper:,.1f}]"
    print(f"{r.target_feature_name}: {r.predicted_value:,.1f}{band}")
    print("[stored and read back from DemandForecast.model_predictions]")


if __name__ == "__main__":
    main()
