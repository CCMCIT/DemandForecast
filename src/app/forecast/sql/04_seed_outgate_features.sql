/*
================================================================================
 Chassis Demand Forecasting - Seed 04: out-gate model features
================================================================================
 Purpose : Seed features_tbl with the rows the per-length out-gate models
           reference, so usp_register_model (called by
           pipelines/outgate_train_run.py) can resolve every feature_id instead
           of tripping the FK. As with seed 03, the write surface has no
           feature-creation proc by design; feature rows are dimension data and
           are seeded here.

           Rows seeded:
             - outgate_transactions_daily_<20|40|45>ft
                   the model TARGETS - daily on-dock out-gate truck moves per
                   chassis length, from GateActivityDetail_tbl (Transactions,
                   GateTypeId = 2, Garden City locations only).
             - imports_prior_4d_<20|40|45>ft
                   forecast loaded import containers of that length discharged
                   over the 4 days BEFORE the target date, from VoyageDetails_tbl
                   (Mode = Vessel, Direction = Import). Read point-in-time, so
                   the stored feature reflects what was knowable at run time.
             - month_of_year_<Month> x12
                   calendar indicator predictors. The fit drops one month as the
                   baseline (folded into the intercept), so only 11 ever carry a
                   coefficient - all 12 are seeded so the seed is robust to which
                   one is dropped, exactly as seed 03 does for weekdays.

           NOT seeded here (already present from seed 03, reused as-is):
             - (Intercept)
             - day_of_week_<Day> x7

           Note the out-gate models share seed 03's day_of_week_* rows rather
           than defining their own. A feature row is a CONCEPT; the coefficient
           fitted against it is per-model and lives in model_coefficients_tbl.

 Idempotent : set-based anti-join insert - only feature_names not already
              present are inserted. Existing rows and their temporal history are
              left untouched, so a re-run inserts nothing and records no
              spurious change.

 Apply AFTER 00_forecast_model.sql and 03_seed_day_of_week_features.sql. Keep
 the names below in sync with forecast/outgate_features.py
 (target_feature_name / imports_feature_name / MONTH_PREFIX); if you rename a
 feature, rename it in BOTH places.
================================================================================
*/

SET NOCOUNT ON;

-- Acting account recorded on the seeded rows (schema default is ORIGINAL_LOGIN();
-- we pass the acting login explicitly, per the "record WHO on every write" convention).
DECLARE @modified_by NVARCHAR(128) = SUSER_SNAME();

DECLARE @gate_source   NVARCHAR(150) = N'DemandForecast.GateActivityDetail_tbl';
DECLARE @voyage_source NVARCHAR(150) = N'DemandForecast.VoyageDetails_tbl';

;WITH lengths (equip_length) AS
(
    SELECT 20 UNION ALL SELECT 40 UNION ALL SELECT 45
),
months (month_number, month_name) AS
(
                  SELECT  1, N'January'
    UNION ALL     SELECT  2, N'February'
    UNION ALL     SELECT  3, N'March'
    UNION ALL     SELECT  4, N'April'
    UNION ALL     SELECT  5, N'May'
    UNION ALL     SELECT  6, N'June'
    UNION ALL     SELECT  7, N'July'
    UNION ALL     SELECT  8, N'August'
    UNION ALL     SELECT  9, N'September'
    UNION ALL     SELECT 10, N'October'
    UNION ALL     SELECT 11, N'November'
    UNION ALL     SELECT 12, N'December'
),
desired (feature_name, description, data_source, unit_of_measure) AS
(
    -- targets: one per chassis length
    SELECT
        CONCAT(N'outgate_transactions_daily_', equip_length, N'ft'),
        CONCAT(N'Daily count of on-dock out-gate truck moves taking a ',
               equip_length, N'ft chassis (model target).'),
        @gate_source,
        N'transactions/day'
    FROM lengths

    UNION ALL

    -- predictors: forecast import window, one per chassis length
    SELECT
        CONCAT(N'imports_prior_4d_', equip_length, N'ft'),
        CONCAT(N'Forecast loaded import containers of ', equip_length,
               N'ft discharged over the 4 days before the target date ',
               N'(target date excluded); read as of the scoring run lead time.'),
        @voyage_source,
        N'containers'
    FROM lengths

    UNION ALL

    -- predictors: month-of-year indicators
    SELECT
        CONCAT(N'month_of_year_', month_name),
        CONCAT(N'Indicator: observation_date falls in ', month_name, N'.'),
        N'Derived from Date (month_name())',
        N'indicator (0/1)'
    FROM months
)
INSERT INTO DemandForecast.features_tbl
    (feature_name, description, data_source, unit_of_measure, is_active, modified_by)
SELECT d.feature_name, d.description, d.data_source, d.unit_of_measure, 1, @modified_by
FROM desired AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM DemandForecast.features_tbl AS f
    WHERE f.feature_name = d.feature_name
);

PRINT CONCAT(N'Seed 04: inserted ', @@ROWCOUNT, N' new feature row(s) into features_tbl.');
GO
