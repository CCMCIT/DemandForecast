"""Pure feature construction for the out-gate models. No I/O, no DB.

Sits beside training.py and feeds it: this module turns the two source reads
(daily out-gates, forecast import window) into the (design, target) pair
training.fit_ols expects. Unit-testable against a hand-built frame.

Why this exists rather than reusing pipelines.train_run.run_training: that
orchestrator sources its design matrix from actuals_tbl, and two of these three
predictor blocks cannot live there.

  - Calendar dummies are derived, not measured - the same reason
    day_of_week_train_run.py builds its own design.
  - The import window is a FORECAST, and its value for a given observation_date
    depends on WHEN you asked. actuals_tbl holds one realized value per
    (feature_id, observation_date) by unique constraint, so it has nowhere to
    put "the 4-day import forecast as it stood 4 days out" alongside "as it
    stood on the day". Storing one vintage there would silently pick a winner.

The target IS a measured quantity and does belong in actuals_tbl - the pipeline
upserts it there so model_predictions can join predictions to ground truth.
"""
from __future__ import annotations

import calendar
from typing import Sequence, Tuple

import pandas as pd

# Baselines are folded into the intercept by drop_first. Explicit ordered
# categoricals make WHICH level gets dropped deterministic and documented,
# rather than an accident of alphabetical ordering.
DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_ORDER = [calendar.month_name[m] for m in range(1, 13)]
DOW_BASELINE = DOW_ORDER[0]        # Monday
MONTH_BASELINE = MONTH_ORDER[0]    # January

DOW_PREFIX = "day_of_week"         # matches the rows seeded by sql/03
MONTH_PREFIX = "month_of_year"


def target_feature_name(equip_length: int) -> str:
    return f"outgate_transactions_daily_{equip_length}ft"


def imports_feature_name(equip_length: int, lookback_days: int) -> str:
    """Per-length: the 20ft model's import input is a different quantity from
    the 45ft model's, so features_tbl should not pretend they are one row."""
    return f"imports_prior_{lookback_days}d_{equip_length}ft"


def daily_frame(
    outgates: pd.DataFrame,      # observation_date, equip_length, outgate_transactions
    imports: pd.DataFrame,       # observation_date, equip_length, imports_prior_window
    equip_length: int,
    *,
    lookback_days: int = 4,
) -> pd.DataFrame:
    """One dense daily row per calendar date for a single chassis length.

    Days absent from the gate feed are real closures - no gate moves happened -
    so the calendar spine is zero-filled rather than dropped. Dropping them
    would fit the day-of-week coefficients on open days only and badly overstate
    the weekend levels.

    Dates with no import rows are likewise genuine zeros (no vessel worked).
    This assumes voyage coverage extends `lookback_days` before the window
    start; otherwise the first few rows carry short windows that read as low
    import volume rather than as missing data.
    """
    imports_column = imports_feature_name(equip_length, lookback_days)

    gate = (
        outgates.loc[outgates["equip_length"] == equip_length,
                     ["observation_date", "outgate_transactions"]]
        .assign(observation_date=lambda d: pd.to_datetime(d["observation_date"]))
    )
    if gate.empty:
        raise ValueError(f"No on-dock out-gate activity for {equip_length}ft.")

    voyage = (
        imports.loc[imports["equip_length"] == equip_length,
                    ["observation_date", "imports_prior_window"]]
        .assign(observation_date=lambda d: pd.to_datetime(d["observation_date"]))
        .rename(columns={"imports_prior_window": imports_column})
    )

    frame = gate.merge(voyage, on="observation_date", how="outer").set_index("observation_date")
    spine = pd.date_range(frame.index.min(), frame.index.max(), freq="D")
    return (
        frame.reindex(spine)
        .fillna(0.0)
        .astype(float)
        .rename_axis("observation_date")
        .reset_index()
    )


def build_design(
    frame: pd.DataFrame,
    equip_length: int,
    *,
    lookback_days: int = 4,
) -> Tuple[pd.DataFrame, pd.Series]:
    """(design, target) for one chassis length, ready for training.fit_ols.

    The design carries NO constant column - fit_ols adds '(Intercept)' itself.
    Dummy columns are named to match the feature_name rows in features_tbl.

    A month absent from the window yields an all-zero column, which is perfectly
    collinear with nothing but contributes no information and inflates the
    parameter count; those are dropped so the fit stays full rank on short
    histories.
    """
    dates = pd.to_datetime(frame["observation_date"])
    imports_column = imports_feature_name(equip_length, lookback_days)

    dow = pd.Categorical(dates.dt.day_name(), categories=DOW_ORDER, ordered=True)
    month = pd.Categorical(dates.dt.month_name(), categories=MONTH_ORDER, ordered=True)

    design = pd.concat(
        [
            pd.get_dummies(dow, prefix=DOW_PREFIX, drop_first=True).astype(float),
            pd.get_dummies(month, prefix=MONTH_PREFIX, drop_first=True).astype(float),
            frame[[imports_column]].astype(float).reset_index(drop=True),
        ],
        axis=1,
    )

    empty = [c for c in design.columns if design[c].sum() == 0.0]
    design = design.drop(columns=empty)

    target = frame["outgate_transactions"].astype(float).reset_index(drop=True)
    design.index = target.index
    return design, target


def retained_feature_names(design: pd.DataFrame) -> Sequence[str]:
    """Feature rows this fit will reference, excluding the intercept."""
    return list(design.columns)
