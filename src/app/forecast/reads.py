"""ReadGateway - named analytical reads, each returning a DataFrame.

Reads never touch a proc; they are one-sided and cheap, so add methods freely as
questions arise. Float is fine for analysis. If you ever read coefficients back
to RE-SCORE (not to eyeball), don't round-trip them as float - carry the
TrainedModel from training instead, or convert explicitly to Decimal.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


class ReadGateway:
    def __init__(self, engine: Engine):
        self._engine = engine

    def active_models(self) -> pd.DataFrame:
        sql = text(
            "SELECT model_id, model_name, model_version, target_feature_id, trained_date "
            "FROM DemandForecast.model_registry_tbl WHERE is_active = 1"
        )
        return pd.read_sql(sql, self._engine)

    def coefficients(self, model_id: int) -> pd.DataFrame:
        sql = text(
            "SELECT feature_id, coefficient_value, std_error, p_value "
            "FROM DemandForecast.model_coefficients_tbl WHERE model_id = :m"
        )
        return pd.read_sql(sql, self._engine, params={"m": model_id})

    def predictions_vs_actuals(self, model_id: int) -> pd.DataFrame:
        """Off the model_predictions view: point, band, lead time, and the
        realized actual joined from actuals_tbl (NULL until backfilled)."""
        sql = text("SELECT * FROM DemandForecast.model_predictions WHERE model_id = :m")
        return pd.read_sql(sql, self._engine, params={"m": model_id})
