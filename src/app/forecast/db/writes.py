"""WriteGateway - the only Python code that performs constrained writes.

Each method maps 1:1 to a stored procedure and passes long-format data as a
table-valued parameter (a list of tuples, which pyodbc binds as a TVP).

Binding rule for TVP numeric columns:
  - COEFFICIENTS bind as Decimal, quantized to the column scale, so the
    DECIMAL(18,8) values the model is reconstructed/inspected from never degrade
    to float on the way in.
  - Every OTHER measure value (inputs, predictions, metrics, actuals) binds as a
    plain float. Two reasons: (1) these are analysis-grade values stored at
    DECIMAL(18,6) - SQL Server coerces the float to the column scale on insert,
    and reads.py already treats them as float for analysis; (2) it sidesteps a
    pyodbc TVP quirk - pyodbc sizes a TVP's numeric column from the FIRST row's
    Decimal (precision + scale), so a column whose leading row is < 1 (e.g. a
    0/1 indicator input, or r_squared in the metrics frame) gets sized too narrow
    and then raises DataError 22003 on the first later row that has an integer
    part. Floats bind as SQL_DOUBLE and carry no such per-row precision guess.

The write surface is deliberately tiny and stable. Do NOT add write helpers here
that bypass a proc - that is exactly how the hybrid rots.
"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
from sqlalchemy.engine import Engine

_SCALE_4 = Decimal("0.0001")
_SCALE_8 = Decimal("0.00000001")


def _dec(value, scale: Decimal):
    """None/NaN -> None; everything else -> Decimal quantized to the column scale.
    Going through str() avoids carrying binary float noise into the Decimal.
    Used for the high-precision coefficient columns and scalar params only."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return Decimal(str(value)).quantize(scale)


def _f(value):
    """None/NaN -> None; everything else -> float. Used for TVP measure columns
    (inputs / predictions / metrics / actuals) so pyodbc binds SQL_DOUBLE and the
    server coerces to the column's DECIMAL scale - no per-row precision guess."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return float(value)


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
            (int(r.feature_id), _as_date(r.target_date), _f(r.feature_value), bool(r.is_forecasted_value))
            for r in inputs.itertuples(index=False)
        ]
        prediction_rows = [
            (_as_date(r.target_date), _f(r.predicted_value),
             _f(r.predicted_lower), _f(r.predicted_upper))
            for r in predictions.itertuples(index=False)
        ]
        # interval_confidence_level is a SCALAR proc param (DECIMAL(5,4)), not a
        # TVP row, so it is unaffected by the per-row inference and stays Decimal.
        conf = _dec(interval_confidence_level, _SCALE_4) if interval_confidence_level is not None else None
        sql = "{CALL DemandForecast.usp_score_run (?, ?, ?, ?, ?, ?)}"
        params = [model_id, _as_date(as_of_date), conf, input_rows, prediction_rows, modified_by]
        return int(self._call_scalar(sql, params))

    # -- ground truth ------------------------------------------------------

    def upsert_actuals(self, *, actuals: pd.DataFrame, modified_by: str) -> None:
        """actuals: feature_id, observation_date, actual_value."""
        rows = [
            (int(r.feature_id), _as_date(r.observation_date), _f(r.actual_value))
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
        # Coefficients stay Decimal: DECIMAL(18,8) exactness for re-scoring.
        coef_rows = [
            (int(r.feature_id), _dec(r.coefficient_value, _SCALE_8),
             _dec(r.std_error, _SCALE_8), _dec(r.p_value, _SCALE_8))
            for r in coefficients.itertuples(index=False)
        ]
        # Metrics are analysis-grade diagnostics -> float (see module docstring).
        metric_rows = [
            (str(r.metric_name), _f(r.metric_value))
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
