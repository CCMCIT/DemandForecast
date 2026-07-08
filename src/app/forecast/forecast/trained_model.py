"""TrainedModel - a model as DATA, not as a database client.

This is the surviving good half of the single-class instinct: a cohesive
in-memory representation of a fitted model, with the DB access stripped out. It
is produced by the training step (which holds the design matrix), carries only
what scoring needs, and delegates the actual math to the pure functions in
scoring.py so those stay independently testable.

Field alignment: coefficients, xtx_inv, and feature_order all share one column
order, with the intercept feature in its position. design_vector substitutes 1.0
for the intercept so callers never store a synthetic 1.0 input row.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from forecast.scoring import predict_point, prediction_interval


@dataclass(frozen=True, eq=False)  # eq=False: ndarray fields make generated __eq__ ambiguous
class TrainedModel:
    model_id: int
    intercept_feature_id: int
    feature_order: tuple[int, ...]   # column order; includes the intercept feature
    coefficients: np.ndarray         # aligned to feature_order
    xtx_inv: np.ndarray              # (X'X)^-1, aligned to feature_order
    residual_std_error: float
    residual_df: int

    def design_vector(self, features: Mapping[int, float]) -> np.ndarray:
        """Order the feature map into the model's column order; 1.0 for the intercept."""
        return np.array(
            [1.0 if f == self.intercept_feature_id else features[f] for f in self.feature_order],
            dtype=float,
        )

    def predict(self, features: Mapping[int, float]) -> float:
        return predict_point(self.coefficients, self.design_vector(features))

    def interval(self, features: Mapping[int, float], confidence_level: float):
        x0 = self.design_vector(features)
        point = predict_point(self.coefficients, x0)
        return prediction_interval(
            point, x0, self.xtx_inv, self.residual_std_error, self.residual_df, confidence_level
        )
