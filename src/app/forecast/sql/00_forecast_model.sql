/*
================================================================================
 Chassis Demand Forecasting - Model Storage Schema
================================================================================
 Purpose : Long-term, production storage for regression model coefficients,
           historical inputs, and predictions. Generic enough to store runs
           for ANY linear-regression target (chassis counts and the upstream
           features that are themselves modeled), not chassis counts alone.
           Multiple models may be active concurrently (for comparison and for
           ensembling several forecasts of the same target).
 Design  : - features_tbl is a dimension table: the single source of truth for
             every parameter the model can use, AND for every quantity a model
             can predict (a model's target is just a feature row). Stock, flow,
             and dwell are DISTINCT feature rows with their own unit_of_measure
             (e.g. 'chassis_dispatched_daily' = flow, 'chassis_on_hire_concurrent'
             = stock, 'avg_dwell_days' = duration). The plan is to model the
             gate-observable flow and dwell and derive concurrent stock by
             chaining them (see is_forecasted_value), so the modeled targets
             come from clean, uncensored gate data.
           - actuals_tbl is the single ground truth: one realized value per
             feature per observation_date, shared by every model and ensemble.
             Predictions do NOT store their own actual_value; accuracy comes
             from joining predictions to actuals on (target_feature_id /
             feature_id, target_date / observation_date).
           - Horizon model: an input batch is one SCORING RUN of one model,
             made as_of_date (the data cutoff), and it fans out across a
             multi-day horizon. The per-day grain lives on model_inputs_tbl
             and model_predictions_tbl via target_date, so forecasting the next
             14 days is one batch + 14 prediction rows, not 14 batches.
           - Prediction intervals: predicted_lower/predicted_upper are a
             PREDICTION interval (a new observation), not a mean-response
             confidence interval - the band the business stages against. They
             are computed in Python at scoring time (T-SQL/Qlik cannot invert
             the t-distribution or rebuild the leverage term) and stored; the
             confidence level lives once per run on model_input_batches_tbl.
           - Diagnostics are in-sample (training-time). Per-coefficient
             std_error/p_value sit on model_coefficients_tbl; whole-model
             diagnostics are rows in model_metrics_tbl. Out-of-sample accuracy
             is derived from predictions vs. actuals_tbl, not stored.
           - Long/EAV layout for coefficients, inputs, and metrics so a model
             version can reference any subset of features (or report any set of
             metrics) without altering table structure.
           - All tables are SQL Server system-versioned temporal tables
             (SQL Server 2019+) so every change is automatically tracked in a
             paired history table (ValidFrom/ValidTo cover created/updated).
           - modified_by captures WHO made a change (temporal tracks WHEN, not
             WHO). Defaults to ORIGINAL_LOGIN(); callers/stored procedures
             should pass the acting user/service account on every write.

 Conventions (per CCM IT review):
           - Base tables (and their system-versioned history tables) are
             suffixed _tbl. NOTE: if the convention exempts system-managed
             history tables, drop _tbl from the *_history_tbl names.
           - Views take no prefix or suffix.

 Notes   : Idempotent - safe to re-run. Intended for version control (GitHub).
================================================================================
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'DemandForecast')
    EXEC('CREATE SCHEMA DemandForecast');
GO

--------------------------------------------------------------------------------
-- 1. features_tbl
--    Dimension table - the canonical list of every parameter a model can use
--    as an input AND every quantity a model can predict, including the
--    intercept (stored as a row named '(Intercept)'). data_source is a plain
--    descriptive label for where the feature originates.
--------------------------------------------------------------------------------
IF OBJECT_ID('DemandForecast.features_tbl') IS NULL
BEGIN
    CREATE TABLE DemandForecast.features_tbl
    (
        feature_id       INT IDENTITY(1,1)      NOT NULL,
        feature_name     NVARCHAR(100)           NOT NULL,   -- canonical name, e.g. "vessel_count"
        description      NVARCHAR(500)           NULL,
        data_source      NVARCHAR(150)           NULL,       -- e.g. "Port AIS feed", "TMS booking export"
        unit_of_measure  NVARCHAR(50)            NULL,
        is_active        BIT                     NOT NULL DEFAULT 1,  -- still being collected/used
        modified_by      NVARCHAR(128)           NOT NULL DEFAULT ORIGINAL_LOGIN(),
        ValidFrom        DATETIME2 GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        ValidTo          DATETIME2 GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_features PRIMARY KEY CLUSTERED (feature_id),
        CONSTRAINT UQ_features_name UNIQUE (feature_name),
        PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.features_history_tbl));
END
GO

--------------------------------------------------------------------------------
-- 2. model_registry_tbl
--    One row per trained model version. target_feature_id declares WHAT the
--    model predicts (FK to features_tbl), which makes the generic
--    predicted_value in model_predictions_tbl interpretable; kept NOT NULL -
--    every model must have something to predict.
--    model_version defaults to 1 (the first version of a given model_name);
--    later versions pass an explicit value (UQ(model_name, model_version)).
--    No "single active model" guard: multiple models may be active at once
--    for comparison and ensembling. r_squared / rmse live in model_metrics_tbl.
--------------------------------------------------------------------------------
IF OBJECT_ID('DemandForecast.model_registry_tbl') IS NULL
BEGIN
    CREATE TABLE DemandForecast.model_registry_tbl
    (
        model_id          INT IDENTITY(1,1)     NOT NULL,
        model_name        NVARCHAR(150)          NOT NULL,   -- business-facing name
        model_version     INT                    NOT NULL DEFAULT (1),
        target_feature_id INT                    NOT NULL,   -- quantity this model predicts
        trained_date      DATETIME2              NOT NULL DEFAULT SYSUTCDATETIME(),
        is_active         BIT                    NOT NULL DEFAULT 0,
        modified_by       NVARCHAR(128)          NOT NULL DEFAULT ORIGINAL_LOGIN(),
        ValidFrom         DATETIME2 GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        ValidTo           DATETIME2 GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_model_registry PRIMARY KEY CLUSTERED (model_id),
        CONSTRAINT UQ_model_registry_name_version UNIQUE (model_name, model_version),
        CONSTRAINT FK_model_registry_target_feature
            FOREIGN KEY (target_feature_id) REFERENCES DemandForecast.features_tbl (feature_id),
        PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.model_registry_history_tbl));
END
GO

--------------------------------------------------------------------------------
-- 3. model_coefficients_tbl
--    Linear regression coefficients, one row per feature per model version.
--    The intercept is the row whose feature_id points to the '(Intercept)'
--    feature; no separate flag.
--
--    std_error is the fitted coefficient's standard error (the primitive).
--    The t-statistic is derivable on read as coefficient_value / std_error and
--    is NOT stored. p_value IS stored because T-SQL (and Qlik) cannot invert
--    the t-distribution to recompute it. Both are NULL-able: a stored model
--    without published inferential stats is still valid.
--------------------------------------------------------------------------------
IF OBJECT_ID('DemandForecast.model_coefficients_tbl') IS NULL
BEGIN
    CREATE TABLE DemandForecast.model_coefficients_tbl
    (
        coefficient_id      BIGINT IDENTITY(1,1)   NOT NULL,
        model_id            INT                     NOT NULL,
        feature_id          INT                     NOT NULL,
        coefficient_value   DECIMAL(18,8)           NOT NULL,
        std_error           DECIMAL(18,8)           NULL,       -- standard error of the coefficient
        p_value             DECIMAL(9,8)            NULL,       -- two-sided p-value (in [0,1])
        modified_by         NVARCHAR(128)           NOT NULL DEFAULT ORIGINAL_LOGIN(),
        ValidFrom           DATETIME2 GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        ValidTo             DATETIME2 GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_model_coefficients PRIMARY KEY CLUSTERED (coefficient_id),
        CONSTRAINT FK_model_coefficients_model
            FOREIGN KEY (model_id) REFERENCES DemandForecast.model_registry_tbl (model_id),
        CONSTRAINT FK_model_coefficients_feature
            FOREIGN KEY (feature_id) REFERENCES DemandForecast.features_tbl (feature_id),
        CONSTRAINT UQ_model_coefficients_model_feature UNIQUE (model_id, feature_id),
        PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.model_coefficients_history_tbl));
END
GO

--------------------------------------------------------------------------------
-- 4. model_metrics_tbl
--    Long-format, in-sample (training-time) diagnostics, one row per metric
--    per model version. New metrics are new rows, never a schema change.
--    Canonical metric_name values:
--      Fit/accuracy : 'r_squared', 'adj_r_squared', 'rmse', 'mae', 'mape'
--      Significance : 'f_statistic', 'f_pvalue'
--      Selection    : 'aic', 'bic'
--      Spread / dof : 'residual_std_error', 'n_observations', 'residual_df'
--      Residuals    : 'durbin_watson'  (autocorrelation - if this flags, the
--                     stored std_errors/p_values and the prediction-interval
--                     width are understated and should not be trusted as-is)
--    MSE is intentionally NOT stored - it is RMSE^2 (derivable, would drift).
--    NOTE: metric_value is DECIMAL(18,6); p-values below ~1e-6 round to 0
--    (read as "highly significant"). Keep exact tiny p-values in Python.
--------------------------------------------------------------------------------
IF OBJECT_ID('DemandForecast.model_metrics_tbl') IS NULL
BEGIN
    CREATE TABLE DemandForecast.model_metrics_tbl
    (
        model_metric_id   BIGINT IDENTITY(1,1)   NOT NULL,
        model_id          INT                     NOT NULL,
        metric_name       NVARCHAR(50)            NOT NULL,
        metric_value      DECIMAL(18,6)           NOT NULL,
        modified_by       NVARCHAR(128)           NOT NULL DEFAULT ORIGINAL_LOGIN(),
        ValidFrom         DATETIME2 GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        ValidTo           DATETIME2 GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_model_metrics PRIMARY KEY CLUSTERED (model_metric_id),
        CONSTRAINT FK_model_metrics_model
            FOREIGN KEY (model_id) REFERENCES DemandForecast.model_registry_tbl (model_id),
        CONSTRAINT UQ_model_metrics_model_metric UNIQUE (model_id, metric_name),
        PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.model_metrics_history_tbl));
END
GO

--------------------------------------------------------------------------------
-- 5. model_input_batches_tbl
--    One row per SCORING RUN: a single model scored as_of_date (the data
--    cutoff / "as of" date for the run). A run fans out across a horizon of
--    target dates carried on model_inputs_tbl and model_predictions_tbl, so a
--    14-day forecast is ONE batch, not 14. Provenance (model + as_of) is
--    recorded once per run.
--
--    interval_confidence_level is the level of the prediction interval stored
--    on this run's predictions (e.g. 0.9500 = 95%). It is set per run by the
--    scoring pipeline - no default - and lives here (not per prediction row)
--    so Qlik can label the band and old rows stay self-describing. NULL means
--    the run produced point forecasts only.
--------------------------------------------------------------------------------
IF OBJECT_ID('DemandForecast.model_input_batches_tbl') IS NULL
BEGIN
    CREATE TABLE DemandForecast.model_input_batches_tbl
    (
        input_batch_id            BIGINT IDENTITY(1,1)   NOT NULL,
        model_id                  INT                     NOT NULL,
        as_of_date                DATE                    NOT NULL,  -- run / data-cutoff date
        interval_confidence_level DECIMAL(5,4)            NULL,      -- e.g. 0.9500; pipeline-driven
        modified_by               NVARCHAR(128)           NOT NULL DEFAULT ORIGINAL_LOGIN(),
        ValidFrom                 DATETIME2 GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        ValidTo                   DATETIME2 GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_model_input_batches PRIMARY KEY CLUSTERED (input_batch_id),
        CONSTRAINT FK_model_input_batches_model
            FOREIGN KEY (model_id) REFERENCES DemandForecast.model_registry_tbl (model_id),
        PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.model_input_batches_history_tbl));
END
GO

--------------------------------------------------------------------------------
-- 6. model_inputs_tbl
--    Long-format feature values for a given run, per horizon day. target_date
--    is the future date a row's value applies to; inputs that are constant
--    across the horizon are repeated per target_date (cheap and explicit).
--
--    is_forecasted_value supports chained/recursive forecasting: when another
--    model's prediction (model_predictions_tbl.predicted_value) is used as an
--    input feature here, the row is flagged 1. That lets you separate
--    actual-data-driven predictions from forecast-on-forecast predictions when
--    analyzing how error compounds across the horizon.
--------------------------------------------------------------------------------
IF OBJECT_ID('DemandForecast.model_inputs_tbl') IS NULL
BEGIN
    CREATE TABLE DemandForecast.model_inputs_tbl
    (
        input_id             BIGINT IDENTITY(1,1)   NOT NULL,
        input_batch_id       BIGINT                  NOT NULL,
        feature_id           INT                     NOT NULL,
        target_date          DATE                    NOT NULL,  -- horizon day this value applies to
        feature_value        DECIMAL(18,6)           NOT NULL,
        is_forecasted_value  BIT                     NOT NULL DEFAULT 0,
        modified_by          NVARCHAR(128)           NOT NULL DEFAULT ORIGINAL_LOGIN(),
        ValidFrom            DATETIME2 GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        ValidTo              DATETIME2 GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_model_inputs PRIMARY KEY CLUSTERED (input_id),
        CONSTRAINT FK_model_inputs_batch
            FOREIGN KEY (input_batch_id) REFERENCES DemandForecast.model_input_batches_tbl (input_batch_id),
        CONSTRAINT FK_model_inputs_feature
            FOREIGN KEY (feature_id) REFERENCES DemandForecast.features_tbl (feature_id),
        CONSTRAINT UQ_model_inputs_batch_feature_date UNIQUE (input_batch_id, feature_id, target_date),
        PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.model_inputs_history_tbl));
END
GO

--------------------------------------------------------------------------------
-- 7. model_predictions_tbl
--    One row per (run, horizon day). Links to the input batch; model_id,
--    as_of_date, and the target feature are derived from the batch + registry
--    (see view model_predictions). target_date is the forecasted date.
--    predicted_value is model-agnostic and sized to match
--    model_inputs_tbl.feature_value, so a value forecast here can feed another
--    model's inputs without precision loss.
--
--    No actual_value here: ground truth lives once in actuals_tbl and is
--    joined on (target_feature_id, target_date). predicted_lower/upper are the
--    PREDICTION-interval bounds (the band the business stages against),
--    computed in Python at scoring time at the level recorded on the parent
--    batch. NULL when the run produced point forecasts only.
--------------------------------------------------------------------------------
IF OBJECT_ID('DemandForecast.model_predictions_tbl') IS NULL
BEGIN
    CREATE TABLE DemandForecast.model_predictions_tbl
    (
        prediction_id     BIGINT IDENTITY(1,1)   NOT NULL,
        input_batch_id    BIGINT                  NOT NULL,
        target_date       DATE                    NOT NULL,  -- forecasted date
        predicted_value   DECIMAL(18,6)           NOT NULL,
        predicted_lower   DECIMAL(18,6)           NULL,      -- prediction-interval lower bound
        predicted_upper   DECIMAL(18,6)           NULL,      -- prediction-interval upper bound
        modified_by       NVARCHAR(128)           NOT NULL DEFAULT ORIGINAL_LOGIN(),
        ValidFrom         DATETIME2 GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        ValidTo           DATETIME2 GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_model_predictions PRIMARY KEY CLUSTERED (prediction_id),
        CONSTRAINT FK_model_predictions_batch
            FOREIGN KEY (input_batch_id) REFERENCES DemandForecast.model_input_batches_tbl (input_batch_id),
        CONSTRAINT UQ_model_predictions_batch_date UNIQUE (input_batch_id, target_date),
        PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.model_predictions_history_tbl));
END
GO

--------------------------------------------------------------------------------
-- 8. actuals_tbl
--    Single ground truth: the realized value of a feature on a given date,
--    sourced from the gate transaction feed (e.g. chassis_dispatched_daily,
--    avg_dwell_days). One row per (feature_id, observation_date), shared by
--    every model and ensemble - predictions join here for accuracy rather than
--    each storing their own copy. Backfilled/corrected over time; temporal
--    versioning preserves the history of those updates.
--------------------------------------------------------------------------------
IF OBJECT_ID('DemandForecast.actuals_tbl') IS NULL
BEGIN
    CREATE TABLE DemandForecast.actuals_tbl
    (
        actual_id         BIGINT IDENTITY(1,1)   NOT NULL,
        feature_id        INT                     NOT NULL,
        observation_date  DATE                    NOT NULL,  -- date the value was realized
        actual_value      DECIMAL(18,6)           NOT NULL,
        modified_by       NVARCHAR(128)           NOT NULL DEFAULT ORIGINAL_LOGIN(),
        ValidFrom         DATETIME2 GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        ValidTo           DATETIME2 GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_actuals PRIMARY KEY CLUSTERED (actual_id),
        CONSTRAINT FK_actuals_feature
            FOREIGN KEY (feature_id) REFERENCES DemandForecast.features_tbl (feature_id),
        CONSTRAINT UQ_actuals_feature_date UNIQUE (feature_id, observation_date),
        PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.actuals_history_tbl));
END
GO

--------------------------------------------------------------------------------
-- Helpful indexes (active models, runs by as-of date, predictions by
-- forecasted date)
--------------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_model_registry_active')
    CREATE INDEX IX_model_registry_active ON DemandForecast.model_registry_tbl (is_active) INCLUDE (model_name, model_version);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_model_input_batches_as_of')
    CREATE INDEX IX_model_input_batches_as_of ON DemandForecast.model_input_batches_tbl (as_of_date) INCLUDE (model_id);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_model_predictions_target_date')
    CREATE INDEX IX_model_predictions_target_date ON DemandForecast.model_predictions_tbl (target_date) INCLUDE (input_batch_id, predicted_value);
GO

--------------------------------------------------------------------------------
-- Views (no prefix/suffix per convention). CREATE OR ALTER keeps re-runs idempotent.
--------------------------------------------------------------------------------

-- Feature set per model version, read straight from the coefficients.
-- Wrap in FOR JSON PATH if a JSON array shape is needed downstream.
CREATE OR ALTER VIEW DemandForecast.model_features
AS
    SELECT
        mc.model_id,
        mc.feature_id,
        f.feature_name
    FROM DemandForecast.model_coefficients_tbl AS mc
    INNER JOIN DemandForecast.features_tbl AS f
        ON f.feature_id = mc.feature_id;
GO

-- Dashboard-facing prediction feed: the point forecast, its prediction-interval
-- band and confidence level, model / run date / forecasted date / lead time,
-- the target feature, and the realized actual joined from actuals_tbl (NULL
-- until backfilled). Built so Qlik can plot a band and accuracy with zero
-- statistics in the dashboard layer.
CREATE OR ALTER VIEW DemandForecast.model_predictions
AS
    SELECT
        p.prediction_id,
        b.model_id,
        p.input_batch_id,
        b.as_of_date,
        p.target_date,
        DATEDIFF(DAY, b.as_of_date, p.target_date) AS lead_time_days,
        r.target_feature_id,
        tf.feature_name AS target_feature_name,
        p.predicted_value,
        p.predicted_lower,
        p.predicted_upper,
        b.interval_confidence_level,
        a.actual_value,
        p.modified_by
    FROM DemandForecast.model_predictions_tbl AS p
    INNER JOIN DemandForecast.model_input_batches_tbl AS b
        ON b.input_batch_id = p.input_batch_id
    INNER JOIN DemandForecast.model_registry_tbl AS r
        ON r.model_id = b.model_id
    INNER JOIN DemandForecast.features_tbl AS tf
        ON tf.feature_id = r.target_feature_id
    LEFT JOIN DemandForecast.actuals_tbl AS a
        ON a.feature_id = r.target_feature_id
       AND a.observation_date = p.target_date;
GO
