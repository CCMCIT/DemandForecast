"""Pure scoring math - numbers in, numbers out. No I/O, no DB.

These are the parts worth unit-testing against a hand-worked example. The
intercept is handled by convention: the design vector carries a 1.0 in the
intercept column and the coefficient vector carries the intercept coefficient in
the same position, so a point forecast is a plain dot product.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import t as student_t


def predict_point(coefficients, design_vector) -> float:
    """Dot product of coefficients and the aligned design vector."""
    return float(np.asarray(coefficients, dtype=float) @ np.asarray(design_vector, dtype=float))


def prediction_interval(point_estimate, design_vector, xtx_inv, residual_std_error, residual_df, confidence_level):
    """PREDICTION interval for a NEW observation (not a mean-response CI).

    band = point +/- t(alpha/2, df) * s * sqrt(1 + x0' (X'X)^-1 x0)

    The leverage term and the t-inversion are exactly what T-SQL/Qlik cannot do,
    which is why this lives in Python and the resulting bounds are stored.
    """
    alpha = 1.0 - confidence_level
    t_crit = float(student_t.ppf(1.0 - alpha / 2.0, residual_df))

    x0 = np.asarray(design_vector, dtype=float)
    leverage = float(x0 @ np.asarray(xtx_inv, dtype=float) @ x0)
    se_pred = residual_std_error * np.sqrt(1.0 + leverage)

    margin = t_crit * se_pred
    return (point_estimate - margin, point_estimate + margin)
