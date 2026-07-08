/*
================================================================================
 Goldilocks - Write Surface migration 02: usp_register_model versioning
================================================================================
 Supersedes the usp_register_model body defined in 01_types_and_procs.sql.
 Apply AFTER 01 (it depends on the CoefficientRow / MetricRow TVP types, which
 are unchanged here). CREATE OR ALTER keeps this idempotent and re-runnable.

 Why this exists:
   Model-version assignment must be atomic with the insert. Computing
   MAX(model_version)+1 in Python across a separate statement/connection races
   the UNIQUE(model_name, model_version) guard and turns a correct retrain into
   a random failure. Pulling it into the proc keeps a registration exactly what
   the architecture promises everywhere else: ONE server-side transaction.

 Changes vs. 01:
   - @model_version default is now NULL. NULL => the proc assigns the next
     version for @model_name (1 for a new lineage); an explicit value is honored
     as before. A range lock (UPDLOCK, HOLDLOCK) serializes concurrent registers
     of the SAME model_name so two racers can't compute the same next version.
   - NEW @retire_previous_active BIT = 0. When @is_active = 1 AND this flag = 1,
     other currently-active versions of the SAME model_name are set inactive
     first, giving a lineage a single active pointer. Default 0 preserves the
     schema's "multiple models active at once" intent - different model_names
     stay active concurrently for comparison / ensembling.
   - Result set now returns BOTH model_id and model_version (the caller needs
     the assigned version back). Callers reading only the first column
     (_call_scalar) still get model_id unchanged.
================================================================================
*/

CREATE OR ALTER PROCEDURE DemandForecast.usp_register_model
    @model_name             NVARCHAR(150),
    @target_feature_id      INT,
    @coefficients           DemandForecast.CoefficientRow READONLY,
    @metrics                DemandForecast.MetricRow      READONLY,
    @modified_by            NVARCHAR(128),
    @model_version          INT       = NULL,   -- NULL => next version for @model_name
    @trained_date           DATETIME2 = NULL,
    @is_active              BIT       = 0,
    @retire_previous_active BIT       = 0
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        -- Assign the version inside the txn so MAX+1 and the INSERT are atomic.
        -- UPDLOCK + HOLDLOCK take a range lock on this model_name's rows, so a
        -- concurrent register of the same name waits rather than colliding on
        -- UQ(model_name, model_version).
        IF @model_version IS NULL
            SELECT @model_version = ISNULL(MAX(model_version), 0) + 1
            FROM DemandForecast.model_registry_tbl WITH (UPDLOCK, HOLDLOCK)
            WHERE model_name = @model_name;

        -- Optional: retire other active versions of THIS lineage only.
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

        COMMIT TRANSACTION;

        SELECT @model_id AS model_id, @model_version AS model_version;  -- both handed back
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO
