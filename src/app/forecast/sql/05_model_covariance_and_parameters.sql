/*
================================================================================
 Goldilocks - migration 05: store the model, stop re-fitting it
================================================================================
 Apply AFTER 00-04. Idempotent; safe to re-run.

 THE PROBLEM
   A registered model could not be scored from the database. Scoring needs a
   prediction interval, the interval needs the leverage term x0'(X'X)^-1 x0, and
   (X'X)^-1 was the one artefact of the fit nowhere in the schema. So scoring
   re-fitted the model in memory and attached the registered model_id.

   That is fragile in a way that gets worse over time. actuals_tbl is a MERGE
   upsert built for backfill and correction, and the gate feed is reprocessed -
   so "re-fit the same window" is NOT a stable operation. Re-run it months later
   and the coefficients can differ because the source rows changed underneath.
   At that point the model is not corrupted, just unscoreable, with no way back.
   A model whose behaviour depends on the current contents of its source tables
   is not really registered.

 WHAT THIS ADDS
   1. model_covariance_tbl  - (X'X)^-1, the missing piece. Everything else the
      scoring object needs is already stored: coefficients in
      model_coefficients_tbl, residual_std_error and residual_df as rows in
      model_metrics_tbl.
   2. model_parameters_tbl  - what went INTO training (window, lookback, voyage
      vintage, filters). Mirrors model_metrics_tbl's long shape, with a clean
      split: metrics record what came OUT of a fit, parameters what went IN.
      This is what lets scoring take --model-id and nothing else.

 DESIGN NOTES (decided deliberately - see the header of each table)
   - FLOAT, not DECIMAL, for covariance values.
   - Full symmetric matrix, not the upper triangle.
   - (X'X)^-1 stored directly rather than X'X inverted on read.
   - Both axes keyed by feature_id, so column ORDER is never stored.

 MIGRATION
   Models registered before this have no covariance rows and cannot be scored
   from the DB. Re-register them (a training re-run assigns a new version).
   There is deliberately no "fall back to re-fitting" path: that fallback would
   become permanent and would reintroduce exactly the instability above.
================================================================================
*/

--------------------------------------------------------------------------------
-- 1. model_covariance_tbl
--    (X'X)^-1 for one model version, one row per matrix cell.
--
--    WHY BOTH AXES ARE feature_id, NOT A POSITION INDEX
--    The matrix is only meaningful aligned to the coefficient vector. Storing a
--    position index would mean storing column order too, and order could then
--    drift out of sync with model_coefficients_tbl - a silent, catastrophic
--    failure, since a mis-aligned leverage term still produces a plausible
--    number. Keying both axes by feature_id makes alignment intrinsic: the
--    reader pivots against whatever order it read the coefficients in, and any
--    order works. The intercept participates naturally, being a feature row.
--
--    WHY FLOAT AND NOT DECIMAL(18,8)
--    Against the schema's DECIMAL convention, deliberately. These are not
--    business quantities; they are artefacts of a matrix inversion spanning a
--    very wide dynamic range. Off-diagonal terms of well-determined models run
--    many orders of magnitude below 1e-8 and would quantize to exactly zero
--    under DECIMAL(18,8), silently distorting every prediction interval
--    computed from them. FLOAT is IEEE-754 double - precisely what numpy holds
--    and what the fit produced - so the round-trip is lossless. There is no
--    exactness to preserve here, only magnitude range, which is the opposite of
--    the case for coefficient_value.
--
--    WHY THE FULL MATRIX
--    (X'X)^-1 is symmetric, so half the rows are redundant: k=20 stores 400
--    cells instead of 210. Storing the triangle would require every reader to
--    mirror it correctly on load, and a reader that forgets produces a subtly
--    wrong band rather than an error. The redundancy is cheap; the explicitness
--    is worth it.
--------------------------------------------------------------------------------
IF OBJECT_ID('DemandForecast.model_covariance_tbl') IS NULL
BEGIN
    CREATE TABLE DemandForecast.model_covariance_tbl
    (
        model_covariance_id BIGINT IDENTITY(1,1)  NOT NULL,
        model_id            INT                    NOT NULL,
        row_feature_id      INT                    NOT NULL,  -- row axis of (X'X)^-1
        col_feature_id      INT                    NOT NULL,  -- column axis
        covariance_value    FLOAT                  NOT NULL,  -- IEEE-754 double; see header
        modified_by         NVARCHAR(128)          NOT NULL DEFAULT ORIGINAL_LOGIN(),
        ValidFrom           DATETIME2 GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        ValidTo             DATETIME2 GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_model_covariance PRIMARY KEY CLUSTERED (model_covariance_id),
        CONSTRAINT FK_model_covariance_model
            FOREIGN KEY (model_id) REFERENCES DemandForecast.model_registry_tbl (model_id),
        CONSTRAINT FK_model_covariance_row_feature
            FOREIGN KEY (row_feature_id) REFERENCES DemandForecast.features_tbl (feature_id),
        CONSTRAINT FK_model_covariance_col_feature
            FOREIGN KEY (col_feature_id) REFERENCES DemandForecast.features_tbl (feature_id),
        CONSTRAINT UQ_model_covariance_cell UNIQUE (model_id, row_feature_id, col_feature_id),
        PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.model_covariance_history_tbl));
END
GO

--------------------------------------------------------------------------------
-- 2. model_parameters_tbl
--    The training configuration, one row per parameter. Long format for the
--    same reason model_metrics_tbl is: a new knob is a new row, never a schema
--    change.
--
--    parameter_value is NVARCHAR because these are heterogeneous - dates,
--    integers, booleans, and text scopes - and their only consumer is the
--    pipeline that wrote them, which knows each one's type. Typing the column
--    would mean either several nullable typed columns or one table per type;
--    both cost more than they return for configuration data that is written
--    once and read back verbatim. Values are stored in an unambiguous,
--    culture-independent form (ISO-8601 dates, 0/1 for flags).
--
--    Canonical parameter_name values for the out-gate models:
--        train_start_date   ISO date   first observation_date in the fit window
--        train_end_date     ISO date   last observation_date in the fit window
--        lookback_days      integer    width of the import window
--        as_of_lead_days    integer    voyage vintage; 'none' => current values
--        loaded_only        0/1        ContainerLoadedFlag filter
--        equip_length       integer    chassis length this model covers
--        location_scope     text       comma-separated on-dock location codes
--------------------------------------------------------------------------------
IF OBJECT_ID('DemandForecast.model_parameters_tbl') IS NULL
BEGIN
    CREATE TABLE DemandForecast.model_parameters_tbl
    (
        model_parameter_id BIGINT IDENTITY(1,1)  NOT NULL,
        model_id           INT                    NOT NULL,
        parameter_name     NVARCHAR(50)           NOT NULL,
        parameter_value    NVARCHAR(400)          NOT NULL,
        modified_by        NVARCHAR(128)          NOT NULL DEFAULT ORIGINAL_LOGIN(),
        ValidFrom          DATETIME2 GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        ValidTo            DATETIME2 GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_model_parameters PRIMARY KEY CLUSTERED (model_parameter_id),
        CONSTRAINT FK_model_parameters_model
            FOREIGN KEY (model_id) REFERENCES DemandForecast.model_registry_tbl (model_id),
        CONSTRAINT UQ_model_parameters_model_name UNIQUE (model_id, parameter_name),
        PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.model_parameters_history_tbl));
END
GO

--------------------------------------------------------------------------------
-- 3. Covering index for the load path.
--    Loading a model reads every covariance cell for one model_id and pivots it.
--    Without this the read is a scan; the table grows as k^2 per model version.
--------------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_model_covariance_model')
    CREATE INDEX IX_model_covariance_model
        ON DemandForecast.model_covariance_tbl (model_id)
        INCLUDE (row_feature_id, col_feature_id, covariance_value);
GO

--------------------------------------------------------------------------------
-- 4. TVP types for the two new tables.
--    In dbo alongside the existing types (see 01's header for why).
--    NOTE: a TVP type cannot be ALTERed - to change one, drop every proc that
--    references it first.
--------------------------------------------------------------------------------
IF TYPE_ID('dbo.CovarianceRow') IS NULL
    CREATE TYPE dbo.CovarianceRow AS TABLE
    (
        row_feature_id   INT    NOT NULL,
        col_feature_id   INT    NOT NULL,
        covariance_value FLOAT  NOT NULL
    );
GO

IF TYPE_ID('dbo.ParameterRow') IS NULL
    CREATE TYPE dbo.ParameterRow AS TABLE
    (
        parameter_name  NVARCHAR(50)  NOT NULL,
        parameter_value NVARCHAR(400) NOT NULL
    );
GO

--------------------------------------------------------------------------------
-- 5. usp_register_model - supersedes migration 02.
--    Adds @covariance and @parameters. A registration remains ONE server-side
--    transaction: registry row, coefficients, metrics, covariance, parameters,
--    all or nothing. Everything else (version assignment under UPDLOCK/HOLDLOCK,
--    @retire_previous_active, the model_id + model_version result set) is
--    unchanged from 02.
--
--    The two new TVPs are declared last so existing positional callers are not
--    disturbed; both are effectively required in practice - a model registered
--    without covariance cannot be scored.
--------------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE DemandForecast.usp_register_model
    @model_name             NVARCHAR(150),
    @target_feature_id      INT,
    @coefficients           dbo.CoefficientRow READONLY,
    @metrics                dbo.MetricRow      READONLY,
    @modified_by            NVARCHAR(128),
    @model_version          INT       = NULL,   -- NULL => next version for @model_name
    @trained_date           DATETIME2 = NULL,
    @is_active              BIT       = 0,
    @retire_previous_active BIT       = 0,
    @covariance             dbo.CovarianceRow  READONLY,
    @parameters             dbo.ParameterRow   READONLY
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        -- Assign the version inside the txn so MAX+1 and the INSERT are atomic.
        IF @model_version IS NULL
            SELECT @model_version = ISNULL(MAX(model_version), 0) + 1
            FROM DemandForecast.model_registry_tbl WITH (UPDLOCK, HOLDLOCK)
            WHERE model_name = @model_name;

        IF @is_active = 1 AND @retire_previous_active = 1
            UPDATE DemandForecast.model_registry_tbl
            SET is_active   = 0,
                modified_by = @modified_by
            WHERE model_name = @model_name
              AND is_active  = 1;

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

        INSERT INTO DemandForecast.model_covariance_tbl
            (model_id, row_feature_id, col_feature_id, covariance_value, modified_by)
        SELECT @model_id, row_feature_id, col_feature_id, covariance_value, @modified_by
        FROM @covariance;

        INSERT INTO DemandForecast.model_parameters_tbl
            (model_id, parameter_name, parameter_value, modified_by)
        SELECT @model_id, parameter_name, parameter_value, @modified_by
        FROM @parameters;

        -- A model that cannot be scored should not be registered. Coefficients
        -- and covariance must describe the SAME feature set, or the leverage
        -- term is computed against a matrix that does not match the vector.
        DECLARE @coef_count INT = (SELECT COUNT(*) FROM @coefficients);
        DECLARE @cov_count  INT = (SELECT COUNT(*) FROM @covariance);
        IF @cov_count <> @coef_count * @coef_count
            THROW 50005, N'Covariance must be the FULL k x k matrix over exactly the coefficient features.', 1;

        IF EXISTS (
            SELECT 1 FROM @covariance AS c
            WHERE NOT EXISTS (SELECT 1 FROM @coefficients AS k WHERE k.feature_id = c.row_feature_id)
               OR NOT EXISTS (SELECT 1 FROM @coefficients AS k WHERE k.feature_id = c.col_feature_id)
        )
            THROW 50006, N'Covariance references a feature with no coefficient row.', 1;

        COMMIT TRANSACTION;

        SELECT @model_id AS model_id, @model_version AS model_version;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO

--------------------------------------------------------------------------------
-- 6. model_definition - one row per stored model, for eyeballing what is
--    registered and whether it is scoreable. Views take no prefix/suffix.
--------------------------------------------------------------------------------
CREATE OR ALTER VIEW DemandForecast.model_definition
AS
    SELECT
        r.model_id,
        r.model_name,
        r.model_version,
        r.trained_date,
        r.is_active,
        tf.feature_name AS target_feature_name,
        (SELECT COUNT(*) FROM DemandForecast.model_coefficients_tbl AS c
          WHERE c.model_id = r.model_id) AS coefficient_count,
        (SELECT COUNT(*) FROM DemandForecast.model_covariance_tbl AS v
          WHERE v.model_id = r.model_id) AS covariance_cell_count,
        (SELECT COUNT(*) FROM DemandForecast.model_parameters_tbl AS p
          WHERE p.model_id = r.model_id) AS parameter_count,
        CAST(CASE
            WHEN (SELECT COUNT(*) FROM DemandForecast.model_covariance_tbl AS v
                   WHERE v.model_id = r.model_id) =
                 POWER((SELECT COUNT(*) FROM DemandForecast.model_coefficients_tbl AS c
                         WHERE c.model_id = r.model_id), 2)
             AND EXISTS (SELECT 1 FROM DemandForecast.model_metrics_tbl AS m
                          WHERE m.model_id = r.model_id AND m.metric_name = 'residual_std_error')
             AND EXISTS (SELECT 1 FROM DemandForecast.model_metrics_tbl AS m
                          WHERE m.model_id = r.model_id AND m.metric_name = 'residual_df')
            THEN 1 ELSE 0
        END AS BIT) AS is_scoreable,
        r.modified_by
    FROM DemandForecast.model_registry_tbl AS r
    INNER JOIN DemandForecast.features_tbl AS tf
        ON tf.feature_id = r.target_feature_id;
GO
