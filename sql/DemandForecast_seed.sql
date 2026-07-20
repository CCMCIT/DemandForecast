/* =====================================================================
   DemandForecast — idempotent seed of the lookup tables.
   Seeds LoadType_tbl, LoadStatus_tbl, VoyageStatus_tbl, Mode_tbl,
   Direction_tbl, FieldType_tbl and the equipment-size FieldValue_tbl /
   FieldTypeValue_tbl rows with their exact ids (IDENTITY_INSERT ON)
   so code that references them by id (see src/app/lookups.py) and the writer,
   which resolves Mode/Direction by NAME, both line up.

   Safe to re-run: each MERGE inserts only the rows that are missing
   (WHEN NOT MATCHED BY TARGET), so existing rows are left untouched.

   Gate-activity lookups (LoadType 4, GateType, LengthMatch_tbl) are seeded
   separately in DemandForecast_GateActivity_seed.sql.

   Run after DemandForecast_schema.sql.
   ===================================================================== */

/* ---------- LoadType_tbl ----------
   The file sources. Ids mirror app.lookups.FileType. Gate Activities (4) is
   seeded in DemandForecast_GateActivity_seed.sql. */

SET IDENTITY_INSERT DemandForecast.LoadType_tbl ON;

MERGE DemandForecast.LoadType_tbl AS tgt
USING (VALUES
    (1, N'GPA 9-day vessel'),
    (2, N'NCSPA Imports'),
    (3, N'NCSPA Exports')
) AS src (LoadTypeId, Name)
ON tgt.LoadTypeId = src.LoadTypeId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (LoadTypeId, Name)
    VALUES (src.LoadTypeId, src.Name);

SET IDENTITY_INSERT DemandForecast.LoadType_tbl OFF;
GO

/* ---------- LoadStatus_tbl ----------
   Ids mirror app.lookups.LoadStatus. 1..5 track a file through the
   pipeline phases; 99 is the rolled-back error state. */

SET IDENTITY_INSERT DemandForecast.LoadStatus_tbl ON;

MERGE DemandForecast.LoadStatus_tbl AS tgt
USING (VALUES
    (1,  N'Inserted into Load'),
    (2,  N'Inserted into LoadDetail'),
    (3,  N'Inserted into Header'),
    (4,  N'Inserted into Detail'),
    (5,  N'Inserted into FieldMap and all relevant tables'),
    (99, N'Error')
) AS src (LoadStatusId, Name)
ON tgt.LoadStatusId = src.LoadStatusId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (LoadStatusId, Name)
    VALUES (src.LoadStatusId, src.Name);

SET IDENTITY_INSERT DemandForecast.LoadStatus_tbl OFF;
GO

/* ---------- VoyageStatus_tbl ----------
   1..3 mirror app.lookups.VoyageStatus; 4 (Error) exists in the DB only. */

SET IDENTITY_INSERT DemandForecast.VoyageStatus_tbl ON;

MERGE DemandForecast.VoyageStatus_tbl AS tgt
USING (VALUES
    (1, N'ToCall',   N'On the current report; expected to call.'),
    (2, N'Called',   N'Fell off the report and was assessed as called.'),
    (3, N'Canceled', N'Fell off the report and was assessed as cancelled.'),
    (4, N'Error',    N'Error happened - See ADMIN.Process_Log_Error_tbl for details')
) AS src (VoyageStatusId, VoyageStatusName, Description)
ON tgt.VoyageStatusId = src.VoyageStatusId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (VoyageStatusId, VoyageStatusName, Description)
    VALUES (src.VoyageStatusId, src.VoyageStatusName, src.Description);

SET IDENTITY_INSERT DemandForecast.VoyageStatus_tbl OFF;
GO

/* ---------- Mode_tbl ----------
   Names must match the mode names in processing/gpa/mapper.py
   (the writer resolves Mode by name). */

SET IDENTITY_INSERT DemandForecast.Mode_tbl ON;

MERGE DemandForecast.Mode_tbl AS tgt
USING (VALUES
    (1, N'Vessel', NULL),
    (2, N'Rail',   NULL),
    (3, N'Truck',  NULL)
) AS src (ModeId, ModeName, Description)
ON tgt.ModeId = src.ModeId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (ModeId, ModeName, Description)
    VALUES (src.ModeId, src.ModeName, src.Description);

SET IDENTITY_INSERT DemandForecast.Mode_tbl OFF;
GO

/* ---------- Direction_tbl ----------
   Names must match the direction names in processing/gpa/mapper.py
   (the writer resolves Direction by name). */

SET IDENTITY_INSERT DemandForecast.Direction_tbl ON;

MERGE DemandForecast.Direction_tbl AS tgt
USING (VALUES
    (1, N'Import'),
    (2, N'Export')
) AS src (DirectionId, DirectionName)
ON tgt.DirectionId = src.DirectionId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (DirectionId, DirectionName)
    VALUES (src.DirectionId, src.DirectionName);

SET IDENTITY_INSERT DemandForecast.Direction_tbl OFF;
GO

/* ---------- FieldType_tbl ----------
   The 8 descriptive field types. Ids mirror app.lookups.FieldType. */

SET IDENTITY_INSERT DemandForecast.FieldType_tbl ON;

MERGE DemandForecast.FieldType_tbl AS tgt
USING (VALUES
    (1, N'Equipment Type', N'dbo.CMST_EquipmentType',   N'code',             N'EquipmentTypeId',   NULL,                               1),
    (2, N'Vessel',         NULL,                         NULL,                NULL,                 NULL,                               0),
    (3, N'Ocean Carrier',  N'dbo.CMST_Company',          N'ShortDisplayName', N'CompanyId',         N'CompanyStatusId = 1',             1),
    (4, N'Service',        NULL,                         NULL,                NULL,                 NULL,                               0),
    (5, N'Location',       N'dbo.CMST_CompanyLocation',  N'Title',            N'CompanyLocationId', N'StatusId = 1',                    1),
    (6, N'Origin Port',    NULL,                         NULL,                NULL,                 NULL,                               0),
    (7, N'Destination Port', NULL,                       NULL,                NULL,                 NULL,                               0),
    (8, N'Trucker',        N'dbo.CMST_Company',          N'ShortDisplayName', N'CompanyId',         N'CompanyStatusId = 1',             1)
) AS src (FieldTypeId, FieldType, ExternalTableName, ExternalSearchColumn, ExternalIdColumn, ExternalWhereClause, ExternalNotifFlag)
ON tgt.FieldTypeId = src.FieldTypeId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (FieldTypeId, FieldType, ExternalTableName, ExternalSearchColumn, ExternalIdColumn, ExternalWhereClause, ExternalNotifFlag)
    VALUES (src.FieldTypeId, src.FieldType, src.ExternalTableName, src.ExternalSearchColumn, src.ExternalIdColumn, src.ExternalWhereClause, src.ExternalNotifFlag);

SET IDENTITY_INSERT DemandForecast.FieldType_tbl OFF;
GO

/* ---------- FieldValue_tbl (equipment container sizes) ----------
   The three GPA container-size values. Ids 1..3 are relied on by
   processing/gpa/mapper.py: GPA_COLUMN_MAP hardcodes
   FieldTypeValueEquipTypeId 1/2/3 (20CH -> 1, 40CH -> 2, 45CH -> 3),
   so these rows and their FieldTypeValue rows must exist with these ids. */

SET IDENTITY_INSERT DemandForecast.FieldValue_tbl ON;

MERGE DemandForecast.FieldValue_tbl AS tgt
USING (VALUES
    (1, N'20CH'),
    (2, N'40CH'),
    (3, N'45CH')
) AS src (FieldValueId, FieldValue)
ON tgt.FieldValueId = src.FieldValueId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (FieldValueId, FieldValue)
    VALUES (src.FieldValueId, src.FieldValue);

SET IDENTITY_INSERT DemandForecast.FieldValue_tbl OFF;
GO

/* ---------- FieldTypeValue_tbl (Equipment Type -> the 3 container sizes) ----------
   Pairs FieldType 1 (Equipment Type) with FieldValue 1..3. ExternalId is
   pre-resolved to the CMST_EquipmentType ids (20CH -> 36, 40CH -> 37,
   45CH -> 38); ExternalNotifFlag is NULL. Mirrors the dev DB. */

SET IDENTITY_INSERT DemandForecast.FieldTypeValue_tbl ON;

MERGE DemandForecast.FieldTypeValue_tbl AS tgt
USING (VALUES
    (1, 1, 1, 36, NULL),
    (2, 1, 2, 37, NULL),
    (3, 1, 3, 38, NULL)
) AS src (FieldTypeValueId, FieldTypeId, FieldValueId, ExternalId, ExternalNotifFlag)
ON tgt.FieldTypeValueId = src.FieldTypeValueId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (FieldTypeValueId, FieldTypeId, FieldValueId, ExternalId, ExternalNotifFlag)
    VALUES (src.FieldTypeValueId, src.FieldTypeId, src.FieldValueId, src.ExternalId, src.ExternalNotifFlag);

SET IDENTITY_INSERT DemandForecast.FieldTypeValue_tbl OFF;
GO