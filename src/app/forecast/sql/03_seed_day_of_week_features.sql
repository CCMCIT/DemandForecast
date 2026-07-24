/*
================================================================================
 Chassis Demand Forecasting - Seed 03: day-of-week model features
================================================================================
 Purpose : Seed features_tbl with the rows the day-of-week model references so
           usp_register_model (called by day_of_week_train_run.py) can resolve
           every feature_id instead of tripping the FK. The write surface has no
           feature-creation proc by design; feature rows are dimension data and
           are seeded here, not through a proc.

           Rows seeded:
             - (Intercept)             : canonical constant-term row, shared by
                                         every model. Insert once; harmless if it
                                         already exists (other models seed it too).
             - gate_transactions_daily : the model TARGET - daily gate-transaction
                                         flow, from the GPA extract's Records column.
             - day_of_week_<Day> x7    : weekday indicator predictors. The fit drops
                                         one weekday as the baseline (folded into the
                                         intercept), so only 6 ever carry a
                                         coefficient - but WHICH day is dropped
                                         depends on the data window. All 7 are seeded
                                         so the seed is robust to that choice; the
                                         baseline day's row simply stays uncoefficiented.

 Idempotent : set-based anti-join insert - only feature_names not already present
              are inserted. Existing rows and their temporal history are left
              untouched, so a re-run inserts nothing and records no spurious change.

 Apply AFTER 00_forecast_model.sql. Keep @target_feature in sync with the --target
 passed to day_of_week_train_run.py (default 'gate_transactions_daily'); if you
 rename the target, rename it in BOTH places.
================================================================================
*/

SET NOCOUNT ON;

-- Acting account recorded on the seeded rows (schema default is ORIGINAL_LOGIN();
-- we pass the acting login explicitly, per the "record WHO on every write" convention).
DECLARE @modified_by    NVARCHAR(128) = SUSER_SNAME();
DECLARE @target_feature NVARCHAR(100) = N'gate_transactions_daily';

;WITH desired (feature_name, description, data_source, unit_of_measure) AS
(
                  SELECT N'(Intercept)',
                         N'Regression intercept / baseline term. Canonical shared row; carries the dropped-category baseline for one-hot models.',
                         NULL, NULL
    UNION ALL     SELECT @target_feature,
                         N'Daily count of gate transactions (model target).',
                         N'GPA Gate Transactions extract (Records column)', N'transactions/day'
    UNION ALL     SELECT N'day_of_week_Monday',    N'Indicator: observation_date falls on a Monday.',    N'Derived from Date (day_name())', N'indicator (0/1)'
    UNION ALL     SELECT N'day_of_week_Tuesday',   N'Indicator: observation_date falls on a Tuesday.',   N'Derived from Date (day_name())', N'indicator (0/1)'
    UNION ALL     SELECT N'day_of_week_Wednesday', N'Indicator: observation_date falls on a Wednesday.', N'Derived from Date (day_name())', N'indicator (0/1)'
    UNION ALL     SELECT N'day_of_week_Thursday',  N'Indicator: observation_date falls on a Thursday.',  N'Derived from Date (day_name())', N'indicator (0/1)'
    UNION ALL     SELECT N'day_of_week_Friday',    N'Indicator: observation_date falls on a Friday.',    N'Derived from Date (day_name())', N'indicator (0/1)'
    UNION ALL     SELECT N'day_of_week_Saturday',  N'Indicator: observation_date falls on a Saturday.',  N'Derived from Date (day_name())', N'indicator (0/1)'
    UNION ALL     SELECT N'day_of_week_Sunday',    N'Indicator: observation_date falls on a Sunday.',    N'Derived from Date (day_name())', N'indicator (0/1)'
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

PRINT CONCAT(N'Seed 03: inserted ', @@ROWCOUNT, N' new feature row(s) into features_tbl.');
GO
