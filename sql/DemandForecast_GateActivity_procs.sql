/* =====================================================================
   DemandForecast — GateActivity procs

   GateActivityFieldTypeValue_upsert
   Find-or-create one (FieldType, FieldValue) pairing and return its id.
   This is steps 1-2 of VoyageFieldMap_upsert, standing on their own: the
   part that resolves a raw string to a FieldTypeValueId, without writing
   any map row.

   GateActivity uses it directly -- its resolved ids (Trucker, Equipment
   Type, Ocean Carrier, Location) are columns on GateActivityDetail_tbl,
   not rows in a field-map table, so only the find-or-create is needed.

   Touches DemandForecast tables only; no external contact. A new
   FieldTypeValue inherits the parent type's ExternalNotifFlag and leaves
   ExternalId NULL, to be filled later by FieldTypeValueExternalId_resolve
   -- identical to how VoyageFieldMap_upsert creates one.

   NOTE: VoyageFieldMap_upsert still holds its own copy of these two steps
   for now (the voyage path is intentionally left untouched). Once that is
   refactored to call this proc, the duplication goes away.
   ===================================================================== */
GO

CREATE OR ALTER PROCEDURE DemandForecast.GateActivityFieldTypeValue_upsert
    @FieldTypeId      int,
    @FieldValue       nvarchar(255),
    @FieldTypeValueId int OUTPUT
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

    COMMIT;
END
GO
