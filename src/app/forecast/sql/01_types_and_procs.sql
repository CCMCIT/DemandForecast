/*
================================================================================
 Goldilocks - Write Surface (TVP types + stored procedures)
================================================================================
 This is the ONLY sanctioned path for constrained writes to the model-storage
 tables. Everything here exists to centralize what the Python layer must not be
 trusted to remember on every call:
   - the hidden ValidFrom/ValidTo period columns are never named (temporal-safe)
   - modified_by is threaded as a parameter, overriding the ORIGINAL_LOGIN()
     default so the ACTING user/service account is recorded, not the connection
   - FK insert order (batch -> inputs -> predictions) is enforced in one place
   - a scoring run is ONE server-side transaction (atomic), not N round-trips
   - actuals is a MERGE upsert (backfill/correction), which to_sql cannot do

 TVP types live in dbo (NOT in DemandForecast). ODBC Driver 17 sends a TVP's
 type name to the server WITHOUT its schema, so a schema-scoped type only
 resolves for a caller whose default schema matches; putting the types in dbo -
 the fallback schema for unqualified name resolution - lets every caller resolve
 them regardless of default schema, with no per-login setup. The tables and the
 procedures themselves stay in DemandForecast; only the parameter TYPES are dbo.

 Idempotent. TVP types use IF TYPE_ID guards. The cleanup preamble below also
 drops the pre-dbo DemandForecast.* TVP types on databases provisioned by an
 earlier version of this script. NOTE: to CHANGE a TVP later you must DROP the
 procedures that reference it first (types cannot be altered) - which is exactly
 what the preamble does.
================================================================================
*/

--------------------------------------------------------------------------------
-- 0. Cleanup preamble (safe on fresh AND already-provisioned databases)
--    Drop the procs first so the TVP types they reference become droppable,
--    then drop the old DemandForecast.* types. Everything is recreated below.
--------------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS DemandForecast.usp_score_run;
DROP PROCEDURE IF EXISTS DemandForecast.usp_upsert_actuals;
DROP PROCEDURE IF EXISTS DemandForecast.usp_register_model;
GO

DROP TYPE IF EXISTS DemandForecast.InputRow;
DROP TYPE IF EXISTS DemandForecast.PredictionRow;
DROP TYPE IF EXISTS DemandForecast.ActualRow;
DROP TYPE IF EXISTS DemandForecast.CoefficientRow;
DROP TYPE IF EXISTS DemandForecast.MetricRow;
GO

--------------------------------------------------------------------------------
-- 1. Table-valued parameter types, in dbo (one per long-format table the
--    pipeline bulk-loads).
--------------------------------------------------------------------------------
IF TYPE_ID('dbo.InputRow') IS NULL
    CREATE TYPE dbo.InputRow AS TABLE
    (
        feature_id          INT            NOT NULL,
        target_date         DATE           NOT NULL,
        feature_value       DECIMAL(18,6)  NOT NULL,
        is_forecasted_value BIT            NOT NULL
    );
GO

IF TYPE_ID('dbo.PredictionRow') IS NULL
    CREATE TYPE dbo.PredictionRow AS TABLE
    (
        target_date     DATE           NOT NULL,
        predicted_value DECIMAL(18,6)  NOT NULL,
        predicted_lower DECIMAL(18,6)  NULL,
        predicted_upper DECIMAL(18,6)  NULL
    );
GO

IF TYPE_ID('dbo.ActualRow') IS NULL
    CREATE TYPE dbo.ActualRow AS TABLE
    (
        feature_id       INT            NOT NULL,
        observation_date DATE           NOT NULL,
        actual_value     DECIMAL(18,6)  NOT NULL
    );
GO

IF TYPE_ID('dbo.CoefficientRow') IS NULL
    CREATE TYPE dbo.CoefficientRow AS TABLE
    (
        feature_id        INT            NOT NULL,
        coefficient_value DECIMAL(18,8)  NOT NULL,
        std_error         DECIMAL(18,8)  NULL,
        p_value           DECIMAL(9,8)   NULL
    );
GO

IF TYPE_ID('dbo.MetricRow') IS NULL
    CREATE TYPE dbo.MetricRow AS TABLE
    (
        metric_name  NVARCHAR(50)   NOT NULL,
        metric_value DECIMAL(18,6)  NOT NULL
    );
GO

--------------------------------------------------------------------------------
-- usp_score_run
--   One atomic scoring run: insert the batch, fan its inputs and predictions
--   across the horizon, commit, and return the new input_batch_id. Called once
--   per run after Python has computed everything (compute-then-commit).
--------------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE DemandForecast.usp_score_run
    @model_id                  INT,
    @as_of_date                DATE,
    @interval_confidence_level DECIMAL(5,4),
    @inputs                    dbo.InputRow      READONLY,
    @predictions               dbo.PredictionRow READONLY,
    @modified_by               NVARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        INSERT INTO DemandForecast.model_input_batches_tbl
            (model_id, as_of_date, interval_confidence_level, modified_by)
        VALUES
            (@model_id, @as_of_date, @interval_confidence_level, @modified_by);

        DECLARE @input_batch_id BIGINT = SCOPE_IDENTITY();

        INSERT INTO DemandForecast.model_inputs_tbl
            (input_batch_id, feature_id, target_date, feature_value, is_forecasted_value, modified_by)
        SELECT @input_batch_id, feature_id, target_date, feature_value, is_forecasted_value, @modified_by
        FROM @inputs;

        INSERT INTO DemandForecast.model_predictions_tbl
            (input_batch_id, target_date, predicted_value, predicted_lower, predicted_upper, modified_by)
        SELECT @input_batch_id, target_date, predicted_value, predicted_lower, predicted_upper, @modified_by
        FROM @predictions;

        COMMIT TRANSACTION;

        SELECT @input_batch_id AS input_batch_id;   -- handed back to the caller
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO

--------------------------------------------------------------------------------
-- usp_upsert_actuals
--   Ground truth lands and gets corrected over time. MERGE on the natural key
--   (feature_id, observation_date) = insert-or-update; only writes on change so
--   the temporal history stays meaningful.
--------------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE DemandForecast.usp_upsert_actuals
    @rows        dbo.ActualRow READONLY,
    @modified_by NVARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        MERGE DemandForecast.actuals_tbl AS tgt
        USING @rows AS src
            ON  tgt.feature_id       = src.feature_id
            AND tgt.observation_date = src.observation_date
        WHEN MATCHED AND tgt.actual_value <> src.actual_value THEN
            UPDATE SET actual_value = src.actual_value,
                       modified_by  = @modified_by
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (feature_id, observation_date, actual_value, modified_by)
            VALUES (src.feature_id, src.observation_date, src.actual_value, @modified_by);

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO

--------------------------------------------------------------------------------
-- usp_register_model
--   Persist a trained model atomically: registry row + coefficients + metrics.
--   model_version defaults to 1; trained_date defaults to now (UTC).
--   NOTE: 02_register_model_versioning.sql supersedes this body with the
--   version-assigning / retire-previous-active variant. Apply 02 after this.
--------------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE DemandForecast.usp_register_model
    @model_name        NVARCHAR(150),
    @target_feature_id INT,
    @coefficients      dbo.CoefficientRow READONLY,
    @metrics           dbo.MetricRow      READONLY,
    @modified_by       NVARCHAR(128),
    @model_version     INT       = 1,
    @trained_date      DATETIME2 = NULL,
    @is_active         BIT       = 0
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        INSERT INTO DemandForecast.model_registry_tbl
            (model_name, model_version, target_feature_id, trained_date, is_active, modified_by)
        VALUES
            (@model_name, @model_version, @target_feature_id,
             COALESCE(@trained_date, SYSUTCDATETIME()), @is_active, @modified_by);

        DECLARE @model_id INT = SCOPE_IDENTITY();

        INSERT INTO DemandForecast.model_coefficients_tbl
            (model_id, feature_id, coefficient_value, std_error, p_value, modified_by)
        SELECT @model_id, feature_id, coefficient_value, std_error, p_value, @modified_by
        FROM @coefficients;

        INSERT INTO DemandForecast.model_metrics_tbl
            (model_id, metric_name, metric_value, modified_by)
        SELECT @model_id, metric_name, metric_value, @modified_by
        FROM @metrics;

        COMMIT TRANSACTION;

        SELECT @model_id AS model_id;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO
