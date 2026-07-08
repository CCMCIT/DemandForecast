"""Pure training math - numbers in, DataFrames/values out. No I/O, no DB.

Mirrors scoring.py's role on the training side: everything here is
unit-testable against a hand-worked fit. The DB round-trip lives in db/, the
wiring in pipelines/.

Two responsibilities:
  1. Turn long actuals into a fitted OLS result (build_design_matrix -> fit_ols).
  2. Shape that result for the write surface (coefficient_frame / metric_frame)
     AND for immediate re-scoring (to_trained_model), so a freshly trained model
     can score without reading its own coefficients back as float.

The intercept is carried by convention: statsmodels' add_constant() emits a
'const' column, which is remapped to the '(Intercept)' feature row - the same
row model_coefficients_tbl stores it under.
"""
from __future__ import annotations

from typing import Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.linear_model import RegressionResultsWrapper
from statsmodels.stats.stattools import durbin_watson

from forecast.trained_model import TrainedModel

INTERCEPT_FEATURE_NAME = "(Intercept)"   # canonical intercept row in features_tbl
_CONST_COL = "const"                      # statsmodels.add_constant() column name


# --- 1. design matrix + fit -------------------------------------------------
def build_design_matrix(
    long_actuals: pd.DataFrame,          # observation_date, feature_name, actual_value
    target_feature: str,
    predictors: Sequence[str],
    *,
    min_observations: int = 20,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Pivot long actuals to (design, target) aligned on observation_date.

    Autoregressive / lagged-target predictors enter as their own feature rows
    (see the lag-0 guard below); the target's own feature at the same date is
    rejected as leakage.

    NA handling is deliberately minimal: any date missing a value for any
    requested feature is dropped (listwise deletion). Imputing or filling NAs -
    like constructing lag features - is a DATA-PREPARATION responsibility handled
    upstream, NOT here. This module is scoped to the prediction modeling and
    assumes actuals arrive analysis-ready; it only drops dates still incomplete.

    Raises on empty/insufficient data or a feature with no actuals so the run
    fails before anything is written.
    """
    predictors = list(predictors)
    if not predictors:
        raise ValueError("At least one predictor is required.")
    if len(set(predictors)) != len(predictors):
        raise ValueError(f"Duplicate predictors supplied: {predictors}")
    # A LAGGED target (e.g. yesterday's outgate) is a valid, useful predictor,
    # but this schema has no time-offset: every coefficient/input is FK-bound to
    # a feature at a single date. So a lagged target must enter as its OWN
    # feature row (e.g. 'chassis_outgated_lag1'), which - having a different
    # name - flows through here normally. What we still block is the target's
    # own feature at the SAME date (lag 0), which leaks the label into the fit.
    if target_feature in predictors:
        raise ValueError(
            f"'{target_feature}' appears as its own predictor at the same "
            f"observation_date (lag 0), which leaks the label into the fit. "
            f"A lagged target is valid - represent it as its own feature row "
            f"(e.g. '{target_feature}_lag1'), not the target at the same date."
        )
    if long_actuals.empty:
        raise ValueError("No actuals rows supplied for the requested features/window.")

    wide = long_actuals.pivot(
        index="observation_date", columns="feature_name", values="actual_value"
    )
    names = [target_feature, *predictors]
    absent = set(names) - set(wide.columns)
    if absent:
        raise ValueError(f"No actuals found for features: {sorted(absent)}")

    wide = wide[names].dropna(how="any")   # drop incomplete dates; imputation is data prep, not here
    if len(wide) < min_observations:
        raise ValueError(
            f"Only {len(wide)} complete observations after cleaning; "
            f"need >= {min_observations}."
        )

    target = wide[target_feature].astype(float)
    design = wide[predictors].astype(float)
    return design, target


def fit_ols(design: pd.DataFrame, target: pd.Series) -> RegressionResultsWrapper:
    """Fit OLS with an intercept ('const' column, remapped downstream)."""
    X = sm.add_constant(design, has_constant="add")
    if _CONST_COL not in X.columns:
        raise RuntimeError("Intercept column was not added; check the design matrix.")
    return sm.OLS(target, X).fit()


# --- 2a. shape for the write surface ---------------------------------------
def _feature_names(res) -> list[str]:
    return [INTERCEPT_FEATURE_NAME if n == _CONST_COL else n for n in res.params.index]


def coefficient_frame(res) -> pd.DataFrame:
    """Rows of (feature_name, coefficient_value, std_error, p_value) as plain
    floats. Decimal quantization is the write surface's job (_dec), not ours.

    coefficient_value must be finite (it is NOT NULL); a non-finite one means a
    degenerate fit, so we raise rather than hand NULL to the proc. std_error /
    p_value may be NaN (perfect collinearity) - _dec maps those to NULL."""
    df = pd.DataFrame(
        {
            "feature_name": _feature_names(res),
            "coefficient_value": res.params.to_numpy(dtype=float),
            "std_error": res.bse.to_numpy(dtype=float),
            "p_value": res.pvalues.to_numpy(dtype=float),
        }
    )
    bad = df.loc[~np.isfinite(df["coefficient_value"]), "feature_name"].tolist()
    if bad:
        raise ValueError(f"Non-finite coefficient(s) for {bad}; fit is degenerate.")
    return df


def metric_frame(res) -> pd.DataFrame:
    """In-sample diagnostics as (metric_name, metric_value) rows. Metric names
    match the canonical set on model_metrics_tbl. Non-finite metrics are dropped
    rather than stored."""
    resid = np.asarray(res.resid, dtype=float)
    nobs = float(res.nobs)
    raw = {
        "r_squared": float(res.rsquared),
        "adj_r_squared": float(res.rsquared_adj),
        "rmse": float(np.sqrt(res.ssr / nobs)),           # sqrt(mean squared resid)
        "mae": float(np.mean(np.abs(resid))),
        "residual_std_error": float(np.sqrt(res.scale)),  # sqrt(ssr / df_resid)
        "f_statistic": float(res.fvalue),
        "f_pvalue": float(res.f_pvalue),
        "aic": float(res.aic),
        "bic": float(res.bic),
        "durbin_watson": float(durbin_watson(resid)),
        "n_observations": nobs,
        "residual_df": float(res.df_resid),
    }
    mape = _mape(res)
    if mape is not None:
        raw["mape"] = mape

    rows = [(name, value) for name, value in raw.items() if np.isfinite(value)]
    return pd.DataFrame(rows, columns=["metric_name", "metric_value"])


def _mape(res) -> float | None:
    """MAPE (percent) over non-zero actuals; None if every actual is zero."""
    actual = np.asarray(res.model.endog, dtype=float)
    fitted = np.asarray(res.fittedvalues, dtype=float)
    mask = actual != 0.0
    if not mask.any():
        return None
    return float(np.mean(np.abs((actual[mask] - fitted[mask]) / actual[mask])) * 100.0)


# --- 2b. shape for immediate re-scoring ------------------------------------
def to_trained_model(res, *, model_id: int, feature_id_of: Mapping[str, int]) -> TrainedModel:
    """Build the in-memory TrainedModel scoring consumes, aligned to the fit's
    column order (intercept first, as add_constant places it).

    xtx_inv is statsmodels' normalized_cov_params = (X'X)^-1, exactly the
    leverage matrix prediction_interval() expects; residual_std_error = sqrt(scale).
    This is the loop-closer that lets a run score without a lossy float
    round-trip through the DB.
    """
    order_names = _feature_names(res)
    return TrainedModel(
        model_id=model_id,
        intercept_feature_id=feature_id_of[INTERCEPT_FEATURE_NAME],
        feature_order=tuple(feature_id_of[n] for n in order_names),
        coefficients=res.params.to_numpy(dtype=float),
        xtx_inv=np.asarray(res.normalized_cov_params, dtype=float),
        residual_std_error=float(np.sqrt(res.scale)),
        residual_df=int(res.df_resid),
    )
