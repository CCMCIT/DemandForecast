/* =====================================================================
   DemandForecast — external id resolution + notify-flag maintenance
   Naming convention: <Entity>[<Column>]_<verb>, entity = table modified.

   Against the 7/8/2026 DDL:
     - FieldType_tbl now exposes ExternalSearchColumn / ExternalIdColumn /
       ExternalWhereClause (all nvarchar(max)), and ExternalNotifFlag is
       now NOT NULL DEFAULT 0.
     - Voyage row population into VoyageFieldMap_tbl is handled in Python;
       the former VoyageFieldMap_populate proc has been removed.

   Runtime ordering (batch):
     1. LOAD    : Python inserts Voyage rows and calls VoyageFieldMap_upsert
                  per attribute. New values land with ExternalId = NULL.
     2. RESOLVE : after load (or scheduled), EXEC FieldTypeValueExternalId_resolve
                  per externally-mapped FieldTypeId. Re-runnable.
     3. NOTIFY  : downstream surfaces ExternalId IS NULL only where
                  ExternalNotifFlag = 1. (0 stays silent.)

   FieldTypeExternalNotifFlag_set is human-invoked, outside the load loop.
   ===================================================================== */
GO

/* ---------------------------------------------------------------------
   VoyageFieldMap_upsert
   Per-attribute: find-or-create FieldValue, find-or-create FieldTypeValue
   (inheriting the parent type's ExternalNotifFlag; ExternalId left NULL),
   then insert-or-update the single map row for (Voyage, FieldType).
   Touches DemandForecast tables only; no external contact.

   Note: FieldType.ExternalNotifFlag is NOT NULL DEFAULT 0, so a new
   FieldTypeValue inherits 0 (suppress) unless the type was explicitly
   set to 1. Notify is opt-in; 1 is the only notify state.
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE DemandForecast.VoyageFieldMap_upsert
    @VoyageId    int,
    @FieldTypeId int,
    @FieldValue  nvarchar(255)
AS
BEGIN
    SET NOCOUNT, XACT_ABORT ON;
    BEGIN TRAN;

    -- 1) find-or-create the raw value
    DECLARE @FieldValueId int;
    SELECT @FieldValueId = FieldValueId
    FROM   DemandForecast.FieldValue_tbl
    WHERE  FieldValue = @FieldValue;

    IF @FieldValueId IS NULL
    BEGIN
        INSERT DemandForecast.FieldValue_tbl (FieldValue) VALUES (@FieldValue);
        SET @FieldValueId = SCOPE_IDENTITY();
    END

    -- 2) find-or-create the type/value pairing; inherit the type's flag.
    --    ExternalId starts NULL (not yet resolved).
    DECLARE @FieldTypeValueId int;
    SELECT @FieldTypeValueId = FieldTypeValueId
    FROM   DemandForecast.FieldTypeValue_tbl
    WHERE  FieldTypeId = @FieldTypeId AND FieldValueId = @FieldValueId;

    IF @FieldTypeValueId IS NULL
    BEGIN
        INSERT DemandForecast.FieldTypeValue_tbl
               (FieldTypeId, FieldValueId, ExternalId, ExternalNotifFlag)
        SELECT @FieldTypeId, @FieldValueId, NULL, ft.ExternalNotifFlag
        FROM   DemandForecast.FieldType_tbl ft
        WHERE  ft.FieldTypeId = @FieldTypeId;
        SET @FieldTypeValueId = SCOPE_IDENTITY();
    END

    -- 3) upsert the map: one row per voyage per field type
    DECLARE @MapId int;
    SELECT @MapId = vfm.MapId
    FROM   DemandForecast.VoyageFieldMap_tbl  vfm
    JOIN   DemandForecast.FieldTypeValue_tbl  ftv ON ftv.FieldTypeValueId = vfm.FieldTypeValueId
    WHERE  vfm.VoyageId = @VoyageId AND ftv.FieldTypeId = @FieldTypeId;

    IF @MapId IS NULL
        INSERT DemandForecast.VoyageFieldMap_tbl (VoyageId, FieldTypeValueId)
        VALUES (@VoyageId, @FieldTypeValueId);
    ELSE
        UPDATE DemandForecast.VoyageFieldMap_tbl
        SET    FieldTypeValueId = @FieldTypeValueId
        WHERE  MapId = @MapId AND FieldTypeValueId <> @FieldTypeValueId;

    COMMIT;
END
GO

/* ---------------------------------------------------------------------
   FieldTypeValueExternalId_resolve
   Set-based, per FieldType. Looks the external table up (same DB, other
   schema) on an exact value match, narrowed by ExternalWhereClause, and
   writes the external id column into FieldTypeValue.ExternalId.
   No match -> ExternalId = NULL.

   NEVER touches ExternalNotifFlag.
   Re-runnable: a value that becomes available externally later flips
   from NULL to an id on the next run.

   Contract / assumptions:
     - ExternalTableName should be schema-qualified ('ExtSchema.SomeTable').
     - ExternalSearchColumn is not unique on its own; ExternalWhereClause
       narrows the match to a single row. The one-row guarantee rests on
       the admin supplying a sufficient clause.
     - ExternalIdColumn names the id column (currently always the PK).
     - Clause is the bare predicate body (e.g. 'CompanyStatusId = 1');
       this proc supplies WHERE/AND and parenthesizes it.
     - Exact match; external column and FieldValue_tbl must share collation.
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE DemandForecast.FieldTypeValueExternalId_resolve
    @FieldTypeId int
AS
BEGIN
    SET NOCOUNT, XACT_ABORT ON;

    DECLARE @extTableName  sysname,
            @extSearchCol  sysname,
            @extIdCol      sysname,
            @extWhere      nvarchar(max);

    SELECT @extTableName = ft.ExternalTableName,
           @extSearchCol = ft.ExternalSearchColumn,
           @extIdCol     = ft.ExternalIdColumn,
           @extWhere     = ft.ExternalWhereClause
    FROM   DemandForecast.FieldType_tbl ft
    WHERE  ft.FieldTypeId = @FieldTypeId;

    -- not configured for external resolution -> nothing to do
    IF @extTableName IS NULL OR @extSearchCol IS NULL OR @extIdCol IS NULL
        RETURN;

    -- same-DB object; accepts 'Schema.Table' or bare name
    DECLARE @extObjId int = OBJECT_ID(@extTableName);
    IF @extObjId IS NULL
    BEGIN
        RAISERROR('External table "%s" not found.', 16, 1, @extTableName);
        RETURN;
    END

    -- validate BOTH admin-named columns against the catalog before they
    -- ever reach the query text (search column + id column)
    DECLARE @searchCol sysname, @idCol sysname;
    SELECT @searchCol = MAX(CASE WHEN c.name = @extSearchCol THEN c.name END),
           @idCol     = MAX(CASE WHEN c.name = @extIdCol     THEN c.name END)
    FROM   sys.columns c
    WHERE  c.object_id = @extObjId
      AND  c.name IN (@extSearchCol, @extIdCol);

    IF @searchCol IS NULL
    BEGIN
        RAISERROR('Search column "%s" not found on "%s".', 16, 1, @extSearchCol, @extTableName);
        RETURN;
    END
    IF @idCol IS NULL
    BEGIN
        RAISERROR('Id column "%s" not found on "%s".', 16, 1, @extIdCol, @extTableName);
        RETURN;
    END

    DECLARE @qualified nvarchar(258) =
        QUOTENAME(OBJECT_SCHEMA_NAME(@extObjId)) + N'.' + QUOTENAME(OBJECT_NAME(@extObjId));

    -- clause is optional: append " AND (<clause>)" only when non-blank.
    -- parentheses group any OR the admin wrote; blank/whitespace = no filter.
    DECLARE @onExtra nvarchar(max) =
        CASE WHEN NULLIF(LTRIM(RTRIM(@extWhere)), N'') IS NULL
             THEN N''
             ELSE N' AND (' + @extWhere + N')'
        END;

    -- clause lives in the LEFT JOIN's ON (not WHERE): an unmatched value must
    -- still yield ExternalId = NULL, not drop the FieldTypeValue row.
    -- Writes ExternalId only; ExternalNotifFlag is never touched here.
    DECLARE @sql nvarchar(max) = N'
        UPDATE ftv
           SET ftv.ExternalId = x.' + QUOTENAME(@idCol) + N'
        FROM   DemandForecast.FieldTypeValue_tbl ftv
        JOIN   DemandForecast.FieldValue_tbl fv
                 ON fv.FieldValueId = ftv.FieldValueId
        LEFT JOIN ' + @qualified + N' x
                 ON x.' + QUOTENAME(@searchCol) + N' = fv.FieldValue' + @onExtra + N'
        WHERE  ftv.FieldTypeId = @ftid;';

    EXEC sys.sp_executesql @sql, N'@ftid int', @ftid = @FieldTypeId;
END
GO

/* ---------------------------------------------------------------------
   FieldTypeExternalNotifFlag_set
   Human-invoked. Sets the type-level ExternalNotifFlag and cascades it
   unconditionally to every existing value under the type.
     @ExternalNotifFlag = 1  -> notify on unmatched values
     @ExternalNotifFlag = 0  -> suppress (type is unmappable by design)
   The cascade overwrites per-value flags by design: under this model
   there is no coherent value-level exception to a type-level decision.
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE DemandForecast.FieldTypeExternalNotifFlag_set
    @FieldTypeId       int,
    @ExternalNotifFlag bit
AS
BEGIN
    SET NOCOUNT, XACT_ABORT ON;
    BEGIN TRAN;

    -- parent: authoritative decision for the whole attribute
    UPDATE DemandForecast.FieldType_tbl
    SET    ExternalNotifFlag = @ExternalNotifFlag
    WHERE  FieldTypeId = @FieldTypeId;

    -- cascade to existing values under the type
    UPDATE DemandForecast.FieldTypeValue_tbl
    SET    ExternalNotifFlag = @ExternalNotifFlag
    WHERE  FieldTypeId = @FieldTypeId;

    COMMIT;
END
GO
