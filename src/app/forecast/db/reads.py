"""ReadGateway - named analytical reads, each returning a DataFrame.

Reads never touch a proc; they are one-sided and cheap, so add methods freely as
questions arise. Float is fine for analysis. If you ever read coefficients back
to RE-SCORE (not to eyeball), don't round-trip them as float - carry the
TrainedModel from training instead, or convert explicitly to Decimal.
"""
from __future__ import annotations

import datetime as dt
from typing import Sequence

import pandas as pd
from sqlalchemy import bindparam, text
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

    # -- training-support reads -------------------------------------------

    def feature_ids(self, feature_names: Sequence[str]) -> pd.DataFrame:
        """Resolve feature_name -> feature_id. Returns only names that exist;
        the caller diffs against what it asked for to fail fast on unknowns."""
        sql = text(
            "SELECT feature_id, feature_name "
            "FROM DemandForecast.features_tbl "
            "WHERE feature_name IN :names"
        ).bindparams(bindparam("names", expanding=True))
        return pd.read_sql(sql, self._engine, params={"names": list(feature_names)})

    def training_actuals(
        self,
        target_feature: str,
        predictors: Sequence[str],
        start_date: dt.date,
        end_date: dt.date,
    ) -> pd.DataFrame:
        """Long-format ground truth for the target + predictors over the window,
        straight from the single actuals_tbl. Pivoting/cleaning is a pure step in
        forecast.training - this method only does the I/O."""
        names = [target_feature, *predictors]
        sql = text(
            "SELECT a.observation_date, f.feature_name, a.actual_value "
            "FROM DemandForecast.actuals_tbl AS a "
            "INNER JOIN DemandForecast.features_tbl AS f ON f.feature_id = a.feature_id "
            "WHERE f.feature_name IN :names "
            "  AND a.observation_date >= :start_date "
            "  AND a.observation_date <= :end_date "
            "ORDER BY a.observation_date"
        ).bindparams(bindparam("names", expanding=True))
        return pd.read_sql(
            sql,
            self._engine,
            params={"names": names, "start_date": start_date, "end_date": end_date},
        )
