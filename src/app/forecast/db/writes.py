"""WriteGateway - the only Python code that performs constrained writes.

Each method maps 1:1 to a stored procedure and passes long-format data as a
table-valued parameter (a list of tuples, which pyodbc binds as a TVP). Numeric
values are converted to Decimal at the exact column scale so the float64 that
numpy/pandas produce never silently degrades DECIMAL(18,8) on the way in.

The write surface is deliberately tiny and stable. Do NOT add write helpers
here that bypass a proc - that is exactly how the hybrid rots.

pyodbc TVP note: pyodbc sizes a TVP's numeric column from the FIRST row's Decimal
(precision + scale), and every later row must fit that binding. A column whose
first value is < 1 (no integer digits) gets sized too narrow and raises DataError
22003 ("Numeric value out of range") on the first later row that has an integer
part. Keep that in mind for any TVP column whose leading row can be a fraction.
"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
from sqlalchemy.engine import Engine

_SCALE_6 = Decimal("0.000001")
_SCALE_8 = Decimal("0.00000001")


def _dec(value, scale: Decimal):
    """None/NaN -> None; everything else -> Decimal quantized to the column scale.
    Going through str() avoids carrying binary float noise into the Decimal."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return Decimal(str(value)).quantize(scale)


def _as_date(value):
    """Normalize a pandas Timestamp / datetime to a plain date for pyodbc."""
    ts = pd.Timestamp(value)
    return ts.date()


class WriteGateway:
    def __init__(self, engine: Engine):
        self._engine = engine

    # -- scoring run -------------------------------------------------------

    def score_run(
        self,
        *,
        model_id: int,
        as_of_date,
        interval_confidence_level,
        inputs: pd.DataFrame,       # feature_id, target_date, feature_value, is_forecasted_value
        predictions: pd.DataFrame,  # target_date, predicted_value, predicted_lower, predicted_upper
        modified_by: str,
    ) -> int:
        """One atomic run: batch + inputs + predictions. Returns input_batch_id."""
        input_rows = [
            (int(r.feature_id), _as_date(r.target_date), _dec(r.feature_value, _SCALE_6), bool(r.is_forecasted_value))
            for r in inputs.itertuples(index=False)
        ]
        prediction_rows = [
            (_as_date(r.target_date), _dec(r.predicted_value, _SCALE_6),
             _dec(r.predicted_lower, _SCALE_6), _dec(r.predicted_upper, _SCALE_6))
            for r in predictions.itertuples(index=False)
        ]
        conf = _dec(interval_confidence_level, Decimal("0.0001")) if interval_confidence_level is not None else None
        sql = "{CALL DemandForecast.usp_score_run (?, ?, ?, ?, ?, ?)}"
        params = [model_id, _as_date(as_of_date), conf, input_rows, prediction_rows, modified_by]
        return int(self._call_scalar(sql, params))

    # -- ground truth ------------------------------------------------------

    def upsert_actuals(self, *, actuals: pd.DataFrame, modified_by: str) -> None:
        """actuals: feature_id, observation_date, actual_value."""
        rows = [
            (int(r.feature_id), _as_date(r.observation_date), _dec(r.actual_value, _SCALE_6))
            for r in actuals.itertuples(index=False)
        ]
        self._call("{CALL DemandForecast.usp_upsert_actuals (?, ?)}", [rows, modified_by])

    # -- training output ---------------------------------------------------

    def register_model(
        self,
        *,
        model_name: str,
        target_feature_id: int,
        coefficients: pd.DataFrame,  # feature_id, coefficient_value, std_error, p_value
        metrics: pd.DataFrame,       # metric_name, metric_value
        modified_by: str,
        model_version: int | None = None,   # None => proc assigns the next version
        trained_date=None,
        is_active: bool = False,
        retire_previous_active: bool = False,
    ) -> dict:
        """Persist a trained model (registry + coefficients + metrics).

        model_version=None lets usp_register_model assign the next version for
        model_name inside its own transaction (race-safe against the UNIQUE
        guard). retire_previous_active=True, together with is_active=True, also
        deactivates other active versions of this same model_name.

        Returns {"model_id": int, "model_version": int}.
        """
        # Coefficients stay Decimal: they are the DECIMAL(18,8) values the model
        # is reconstructed/inspected from, and the intercept (first row) is wide
        # enough to size the TVP's numeric columns correctly.
        coef_rows = [
            (int(r.feature_id), _dec(r.coefficient_value, _SCALE_8),
             _dec(r.std_error, _SCALE_8), _dec(r.p_value, _SCALE_8))
            for r in coefficients.itertuples(index=False)
        ]
        # metric_value binds as float, NOT Decimal. metric_frame leads with
        # r_squared (< 1), so a Decimal binding would size this TVP column
        # NUMERIC(<=6,6) off that first row and then overflow on the first metric
        # with an integer part (rmse, f_statistic, aic, ...), raising pyodbc
        # DataError 22003. Metrics are analysis-grade diagnostics stored as
        # DECIMAL(18,6); binding float makes pyodbc use SQL_DOUBLE and lets SQL
        # Server coerce to the column scale with no client-side precision guess.
        metric_rows = [
            (str(r.metric_name), float(r.metric_value))
            for r in metrics.itertuples(index=False)
        ]
        sql = "{CALL DemandForecast.usp_register_model (?, ?, ?, ?, ?, ?, ?, ?, ?)}"
        params = [model_name, target_feature_id, coef_rows, metric_rows,
                  modified_by, model_version,
                  _as_date(trained_date) if trained_date is not None else None,
                  int(is_active), int(retire_previous_active)]
        row = self._call_row(sql, params)
        return {"model_id": int(row[0]), "model_version": int(row[1])}

    # -- raw proc plumbing -------------------------------------------------

    def _call(self, sql: str, params: list) -> None:
        raw = self._engine.raw_connection()
        try:
            cursor = raw.cursor()
            cursor.execute(sql, params)
            raw.commit()
        finally:
            raw.close()

    def _call_scalar(self, sql: str, params: list):
        raw = self._engine.raw_connection()
        try:
            cursor = raw.cursor()
            cursor.execute(sql, params)
            value = cursor.fetchone()[0]
            raw.commit()
            return value
        finally:
            raw.close()

    def _call_row(self, sql: str, params: list):
        """Like _call_scalar but returns the whole first row (e.g. a proc that
        hands back model_id AND model_version)."""
        raw = self._engine.raw_connection()
        try:
            cursor = raw.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            raw.commit()
            return row
        finally:
            raw.close()
