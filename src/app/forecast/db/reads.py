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


_IMPORT_WINDOW_SQL = """
WITH spine AS (
    SELECT CAST(:start_date AS DATE) AS target_date
    UNION ALL
    SELECT DATEADD(DAY, 1, target_date)
    FROM spine
    WHERE target_date < CAST(:end_date AS DATE)
),
voyage_detail AS (
    SELECT
        v.WORK_DATE,
        TRY_CONVERT(INT, LEFT(equip.FieldValue, 2)) AS equip_length,
        vd.Containers,
        {period_cols}
    FROM DemandForecast.Voyage_tbl {voyage_period} AS v
    INNER JOIN DemandForecast.VoyageDetails_tbl {detail_period} AS vd
        ON vd.VoyageId = v.VoyageId
    INNER JOIN DemandForecast.FieldTypeValue_tbl AS equip_ftv
        ON equip_ftv.FieldTypeValueId = vd.FieldTypeValueEquipTypeId
       AND equip_ftv.FieldTypeId      = :field_type_equipment
    INNER JOIN DemandForecast.FieldValue_tbl AS equip
        ON equip.FieldValueId = equip_ftv.FieldValueId
    WHERE vd.ModeId              = :mode_vessel
      AND vd.DirectionId         = :direction_import
      AND vd.ContainerLoadedFlag = :loaded_flag
      AND v.VoyageStatusId IN :voyage_statuses
      AND v.WORK_DATE IS NOT NULL
)
SELECT
    s.target_date     AS observation_date,
    d.equip_length,
    SUM(d.Containers) AS imports_prior_window
FROM spine AS s
INNER JOIN voyage_detail AS d
    ON  d.WORK_DATE >= DATEADD(DAY, -:lookback_days, s.target_date)
    AND d.WORK_DATE <  s.target_date
    {temporal_predicate}
WHERE d.equip_length IN :equip_lengths
GROUP BY s.target_date, d.equip_length
OPTION (MAXRECURSION 0)
"""

# Rows valid at midnight UTC on (target_date - as_of_lead_days). Voyage and
# VoyageDetails are system-versioned independently, so both windows must
# bracket that instant.
_TEMPORAL_PREDICATE = """
    AND d.VoyageSysStart <= DATEADD(DAY, -:as_of_lead_days, CAST(s.target_date AS DATETIME2))
    AND d.VoyageSysEnd    > DATEADD(DAY, -:as_of_lead_days, CAST(s.target_date AS DATETIME2))
    AND d.DetailSysStart <= DATEADD(DAY, -:as_of_lead_days, CAST(s.target_date AS DATETIME2))
    AND d.DetailSysEnd    > DATEADD(DAY, -:as_of_lead_days, CAST(s.target_date AS DATETIME2))
"""

_PERIOD_COLS = """
        v.SysStartTime  AS VoyageSysStart,
        v.SysEndTime    AS VoyageSysEnd,
        vd.SysStartTime AS DetailSysStart,
        vd.SysEndTime   AS DetailSysEnd
"""



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
        PRIOR `lookback_days` days, by chassis length. The window is summed in
        SQL rather than by a pandas rolling sum because the point-in-time variant
        needs the window and the temporal bracket in one statement.

        VoyageDetails states the port's forecast in chassis codes (20CH / 40CH /
        45CH and nothing else), so LEFT(FieldValue, 2) yields exactly 20, 40 or
        45 and no container-to-chassis mapping is needed.

        as_of_lead_days=None reads current voyage rows - fine for exploration,
        wrong for training a model that will score on forecasts. Set it to the
        run lead time and each row is read AS IT STOOD on the day the run would
        have been made, so the model learns from forecasts of the same vintage it
        gets in production. Training on current values fits a relationship to
        near-final numbers the scoring job will never have, which inflates
        in-sample fit and quietly degrades live accuracy.

        That is also what makes the VoyageStatus filter honest: a voyage that
        cancels LATER was still ToCall on the day the run was made, and its
        containers belonged in that day's forecast.
        """
        point_in_time = as_of_lead_days is not None
        sql = text(
            _IMPORT_WINDOW_SQL.format(
                voyage_period="FOR SYSTEM_TIME ALL" if point_in_time else "",
                detail_period="FOR SYSTEM_TIME ALL" if point_in_time else "",
                period_cols=_PERIOD_COLS if point_in_time else "CAST(NULL AS INT) AS _unused",
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
            "equip_lengths": list(equip_lengths),
            "voyage_statuses": [int(s) for s in voyage_statuses],
        }
        if point_in_time:
            params["as_of_lead_days"] = as_of_lead_days

        return pd.read_sql(sql, self._engine, params=params, parse_dates=["observation_date"])
