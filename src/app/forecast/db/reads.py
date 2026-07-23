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

from app.lookups import FieldType, VoyageStatus
from forecast import training
from forecast.trained_model import TrainedModel

# Lookup ids with no enum in app.lookups yet. Add them there if they spread
# beyond this module.
OUT_GATE_TYPE_ID = 2   # GateType_tbl:  1 In Gate,  2 Out Gate
MODE_VESSEL = 1        # Mode_tbl:      1 Vessel,   2 Rail,    3 Truck
DIRECTION_IMPORT = 1   # Direction_tbl: 1 Import,   2 Export

CHASSIS_LENGTHS = (20, 40, 45)

# The source system versioned its locations rather than updating them, so on-dock
# Garden City appears twice. CCM treats them as one place. The other GPA
# locations (Ocean Terminal, Inland ARP, Gainesville) are off-dock, out of scope.
ON_DOCK_LOCATION_CODES = ("GPA - Garden City", "GPA - Garden City 3.0")

# A voyage not yet assessed as cancelled still carries containers in the
# forecast. Under a point-in-time read this is evaluated against the row version
# valid at the as-of instant, which is what makes excluding CANCELLED safe
# rather than leaky - see import_window.
FORECASTABLE_VOYAGE_STATUSES = (VoyageStatus.TO_CALL, VoyageStatus.CALLED)


# --- import_window SQL ------------------------------------------------------
#
# Shape note: this does NOT build a date spine and range-join voyages to it.
# A voyage worked on day w contributes to exactly the target dates
# w+1 .. w+lookback_days, so the rows are fanned out over a small day_offsets list
# and target_date is derived. That turns a range join - which SQL Server cannot
# seek, and so nested-loops at (spine rows x voyage rows) - into an equijoin
# against 4 rows. Equivalence:
#     w >= target - lookback AND w < target  <=>  target = w + o, o IN 1..lookback
_IMPORT_WINDOW_SQL = """
WITH equip AS
(
    -- Three rows. VoyageDetails states the port forecast in chassis codes only
    -- (20CH / 40CH / 45CH), so resolving the EAV once here beats joining both
    -- lookup tables against every voyage-detail row.
    SELECT
        ftv.FieldTypeValueId,
        TRY_CONVERT(INT, LEFT(fv.FieldValue, 2)) AS equip_length
    FROM DemandForecast.FieldTypeValue_tbl AS ftv
    INNER JOIN DemandForecast.FieldValue_tbl AS fv
        ON fv.FieldValueId = ftv.FieldValueId
    WHERE ftv.FieldTypeId = :field_type_equipment
      AND fv.FieldValue LIKE '%CH'
      AND TRY_CONVERT(INT, LEFT(fv.FieldValue, 2)) IN :equip_lengths
),
day_offsets AS   -- not "offsets": OFFSETS is a reserved T-SQL keyword
(
    SELECT TOP (:lookback_days)
           ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS day_offset
    FROM sys.all_objects
),
contributions AS
(
    SELECT
        DATEADD(DAY, o.day_offset, v.WORK_DATE) AS target_date,
        e.equip_length,
        vd.Containers{period_cols}
    FROM DemandForecast.Voyage_tbl {voyage_period} AS v
    INNER JOIN DemandForecast.VoyageDetails_tbl {detail_period} AS vd
        ON vd.VoyageId = v.VoyageId
    INNER JOIN equip AS e
        ON e.FieldTypeValueId = vd.FieldTypeValueEquipTypeId
    CROSS JOIN day_offsets AS o
    WHERE vd.ModeId              = :mode_vessel
      AND vd.DirectionId         = :direction_import
      AND vd.ContainerLoadedFlag = :loaded_flag
      AND v.VoyageStatusId IN :voyage_statuses
      AND v.WORK_DATE IS NOT NULL
      AND DATEADD(DAY, o.day_offset, v.WORK_DATE) BETWEEN :start_date AND :end_date
)
SELECT
    c.target_date     AS observation_date,
    c.equip_length,
    SUM(c.Containers) AS imports_prior_window
FROM contributions AS c
{temporal_predicate}
GROUP BY c.target_date, c.equip_length
"""

# The as-of instant is derived from each contribution's OWN target date. Voyage
# and VoyageDetails are system-versioned independently, so both periods must
# contain that instant.
_TEMPORAL_PREDICATE = """
CROSS APPLY (
    SELECT DATEADD(DAY, -:as_of_lead_days, CAST(c.target_date AS DATETIME2)) AS asof
) AS a
WHERE c.VoyageSysStart <= a.asof AND c.VoyageSysEnd > a.asof
  AND c.DetailSysStart <= a.asof AND c.DetailSysEnd > a.asof
"""

_PERIOD_COLS = """,
        v.SysStartTime  AS VoyageSysStart,
        v.SysEndTime    AS VoyageSysEnd,
        vd.SysStartTime AS DetailSysStart,
        vd.SysEndTime   AS DetailSysEnd"""

# Bounded history read. The as-of instants this window can ask about span
# exactly [start - lead, end - lead], so BETWEEN prunes versions that could
# never satisfy the per-row bracket above - which still decides the answer.
# FOR SYSTEM_TIME ALL read every version ever written and discarded most.
_SYSTEM_TIME_PERIOD = "FOR SYSTEM_TIME BETWEEN :asof_min AND :asof_max"



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

    def metrics(self, model_id: int) -> pd.DataFrame:
        """In-sample diagnostics for a model as (metric_name, metric_value)."""
        sql = text(
            "SELECT metric_name, metric_value "
            "FROM DemandForecast.model_metrics_tbl WHERE model_id = :m"
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

    def feature_names(self, feature_ids: Sequence[int]) -> pd.DataFrame:
        """(feature_id, feature_name) for the given ids - the reverse of
        feature_ids(), used when reconstructing a stored model's design."""
        sql = text(
            "SELECT feature_id, feature_name FROM DemandForecast.features_tbl "
            "WHERE feature_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        return pd.read_sql(sql, self._engine, params={"ids": [int(i) for i in feature_ids]})

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

    # -- source reads for the out-gate models ------------------------------

    def daily_outgates(
        self,
        start_date: dt.date,
        end_date: dt.date,
        *,
        equip_lengths: Sequence[int] = CHASSIS_LENGTHS,
        location_codes: Sequence[str] = ON_DOCK_LOCATION_CODES,
    ) -> pd.DataFrame:
        """observation_date, equip_length, outgate_transactions - one row per day
        per chassis length, on-dock out-gates only.

        Keyed on EquipLength rather than the EquipType EAV: length is the grain
        the models split on, and GateActivityDetail's EquipType field mixes
        chassis codes (20CH) with container codes (20STD).

        Transactions, not Units - one truck move takes one chassis, so a doubled
        move carrying two boxes is still a single chassis off the stack.

        The location join is INNER, so rows with a NULL or unrecognized
        FieldTypeValueLocationId drop out rather than silently counting as
        on-dock. If that discards material volume, the location data needs
        cleaning before it needs modeling.
        """
        sql = text(
            """
            SELECT
                g.[Date]            AS observation_date,
                g.EquipLength       AS equip_length,
                SUM(g.Transactions) AS outgate_transactions
            FROM DemandForecast.GateActivityDetail_tbl AS g
            INNER JOIN DemandForecast.FieldTypeValue_tbl AS loc_ftv
                ON loc_ftv.FieldTypeValueId = g.FieldTypeValueLocationId
               AND loc_ftv.FieldTypeId      = :field_type_location
            INNER JOIN DemandForecast.FieldValue_tbl AS loc
                ON loc.FieldValueId = loc_ftv.FieldValueId
            WHERE g.GateTypeId = :out_gate_type_id
              AND g.[Date] BETWEEN :start_date AND :end_date
              AND g.EquipLength IN :equip_lengths
              AND loc.FieldValue IN :location_codes
            GROUP BY g.[Date], g.EquipLength
            """
        ).bindparams(
            bindparam("equip_lengths", expanding=True),
            bindparam("location_codes", expanding=True),
        )
        return pd.read_sql(
            sql,
            self._engine,
            params={
                "field_type_location": int(FieldType.LOCATION),
                "out_gate_type_id": OUT_GATE_TYPE_ID,
                "start_date": start_date,
                "end_date": end_date,
                "equip_lengths": list(equip_lengths),
                "location_codes": list(location_codes),
            },
            parse_dates=["observation_date"],
        )

    def import_window(
        self,
        start_date: dt.date,
        end_date: dt.date,
        *,
        lookback_days: int = 4,
        as_of_lead_days: int | None = None,
        loaded_only: bool = True,
        equip_lengths: Sequence[int] = CHASSIS_LENGTHS,
        voyage_statuses: Sequence[int] = FORECASTABLE_VOYAGE_STATUSES,
    ) -> pd.DataFrame:
        """observation_date, equip_length, imports_prior_window.

        For each target date, the forecast import containers discharged over the
        PRIOR `lookback_days` days, by chassis length. Summed in SQL rather than
        by a pandas rolling sum because the point-in-time variant needs the
        window and the temporal bracket in one statement.

        as_of_lead_days=None reads current voyage rows - fine for exploration,
        wrong for training a model that will score on forecasts. Set it to the
        run lead time and each row is read AS IT STOOD on the day the run would
        have been made, so the model learns from forecasts of the same vintage
        it gets in production. Training on current values fits a relationship to
        near-final numbers the scoring job will never have, which inflates
        in-sample fit and quietly degrades live accuracy.

        That is also what makes the VoyageStatus filter honest: a voyage that
        cancels LATER was still ToCall on the day the run was made, and its
        containers belonged in that day's forecast.
        """
        point_in_time = as_of_lead_days is not None
        sql = text(
            _IMPORT_WINDOW_SQL.format(
                voyage_period=_SYSTEM_TIME_PERIOD if point_in_time else "",
                detail_period=_SYSTEM_TIME_PERIOD if point_in_time else "",
                period_cols=_PERIOD_COLS if point_in_time else "",
                temporal_predicate=_TEMPORAL_PREDICATE if point_in_time else "",
            )
        ).bindparams(
            bindparam("equip_lengths", expanding=True),
            bindparam("voyage_statuses", expanding=True),
        )

        params = {
            "start_date": start_date,
            "end_date": end_date,
            "lookback_days": lookback_days,
            "mode_vessel": MODE_VESSEL,
            "direction_import": DIRECTION_IMPORT,
            "field_type_equipment": int(FieldType.EQUIPMENT_TYPE),
            "loaded_flag": 1 if loaded_only else 0,
            "equip_lengths": [int(v) for v in equip_lengths],
            "voyage_statuses": [int(s) for s in voyage_statuses],
        }
        if point_in_time:
            lead = dt.timedelta(days=as_of_lead_days)
            params["as_of_lead_days"] = as_of_lead_days
            params["asof_min"] = dt.datetime.combine(start_date, dt.time.min) - lead
            params["asof_max"] = dt.datetime.combine(end_date, dt.time.min) - lead

        return pd.read_sql(sql, self._engine, params=params, parse_dates=["observation_date"])

    # -- loading a STORED model --------------------------------------------

    def covariance(self, model_id: int) -> pd.DataFrame:
        """The full (X'X)^-1 for a model as (row_feature_id, col_feature_id,
        covariance_value). FLOAT in, float out - no Decimal round-trip, because
        the stored value IS the model, not an approximation of one held
        elsewhere."""
        sql = text(
            "SELECT row_feature_id, col_feature_id, covariance_value "
            "FROM DemandForecast.model_covariance_tbl WHERE model_id = :m"
        )
        return pd.read_sql(sql, self._engine, params={"m": model_id})

    def model_parameters(self, model_id: int) -> dict[str, str]:
        """Training configuration as {parameter_name: parameter_value}. Values
        are strings by design (see model_parameters_tbl); callers coerce."""
        sql = text(
            "SELECT parameter_name, parameter_value "
            "FROM DemandForecast.model_parameters_tbl WHERE model_id = :m"
        )
        df = pd.read_sql(sql, self._engine, params={"m": model_id})
        return dict(zip(df.parameter_name, df.parameter_value))

    def model_definition(self, model_id: int) -> pd.Series:
        """One row from the model_definition view, including is_scoreable."""
        sql = text("SELECT * FROM DemandForecast.model_definition WHERE model_id = :m")
        df = pd.read_sql(sql, self._engine, params={"m": model_id})
        if df.empty:
            raise ValueError(f"model_id={model_id} is not registered.")
        return df.iloc[0]

    def load_trained_model(self, model_id: int) -> TrainedModel:
        """Reconstruct the scoring object entirely from stored rows.

        This is what replaces re-fitting at scoring time. Everything the
        prediction interval needs is now persisted: coefficients, the full
        (X'X)^-1, and residual_std_error / residual_df from model_metrics_tbl.

        On the float round-trip this module warns about elsewhere: that warning
        is about reading coefficients back to reconstruct a model you already
        hold in memory more precisely. Here the stored rows ARE the model - the
        canonical definition - so reading them as float is not a degradation,
        it is the point. DECIMAL(18,8) sits comfortably inside float64.

        Raises if the model is not scoreable rather than silently substituting a
        partial matrix, because a wrong leverage term still yields a
        plausible-looking band.
        """
        coefficients = self.coefficients(model_id)
        if coefficients.empty:
            raise ValueError(f"model_id={model_id} has no coefficients registered.")

        metrics = self.metrics(model_id)
        by_name = dict(zip(metrics.metric_name, metrics.metric_value))
        for required in ("residual_std_error", "residual_df"):
            if required not in by_name:
                raise ValueError(
                    f"model_id={model_id} has no '{required}' metric; the prediction "
                    "interval cannot be reconstructed."
                )

        intercept = self.feature_ids([training.INTERCEPT_FEATURE_NAME])
        if intercept.empty:
            raise ValueError(
                f"'{training.INTERCEPT_FEATURE_NAME}' is not registered in features_tbl."
            )

        return training.trained_model_from_storage(
            model_id=model_id,
            coefficients=dict(
                zip(coefficients.feature_id.astype(int),
                    coefficients.coefficient_value.astype(float))
            ),
            covariance=self.covariance(model_id),
            residual_std_error=float(by_name["residual_std_error"]),
            residual_df=int(by_name["residual_df"]),
            intercept_feature_id=int(intercept.iloc[0].feature_id),
        )
