/* =====================================================================
   DemandForecast — idempotent seed of the lookup tables.
   Seeds LoadStatus_tbl, VoyageStatus_tbl, Mode_tbl, Direction_tbl and
   FieldType_tbl with their exact ids (IDENTITY_INSERT ON) so code that
   references them by id (see src/app/lookups.py) and the writer, which
   resolves Mode/Direction by NAME, both line up.

   Safe to re-run: each MERGE inserts only the rows that are missing
   (WHEN NOT MATCHED BY TARGET), so existing rows are left untouched.

   Run after DemandForecast_schema.sql.
   ===================================================================== */

/* ---------- LoadStatus_tbl ----------
   Ids mirror app.lookups.LoadStatus. 1..5 track a file through the
   pipeline phases; 99 is the rolled-back error state. */

SET IDENTITY_INSERT DemandForecast.LoadStatus_tbl ON;

MERGE DemandForecast.LoadStatus_tbl AS tgt
USING (VALUES
    (1,  N'Inserted into File'),
    (2,  N'Inserted into FileDetail'),
    (3,  N'Inserted into Voyage'),
    (4,  N'Inserted into VoyageDetail'),
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
   The 7 descriptive field types. Ids mirror app.lookups.FieldType. */

SET IDENTITY_INSERT DemandForecast.FieldType_tbl ON;

MERGE DemandForecast.FieldType_tbl AS tgt
USING (VALUES
    (1, N'Equipment Type', N'dbo.CMST_EquipmentType',   N'code',             N'EquipmentTypeId',   N'EquipmentTypeId in (36, 37, 38)', 1),
    (2, N'Vessel',         NULL,                         NULL,                NULL,                 NULL,                               0),
    (3, N'Ocean Carrier',  N'dbo.CMST_Company',          N'ShortDisplayName', N'CompanyId',         N'CompanyStatusId = 1',             1),
    (4, N'Service',        NULL,                         NULL,                NULL,                 NULL,                               0),
    (5, N'Location',       N'dbo.CMST_CompanyLocation',  N'Title',            N'CompanyLocationId', N'StatusId = 1',                    1),
    (6, N'Origin Port',    NULL,                         NULL,                NULL,                 NULL,                               0),
    (7, N'Destination Port', NULL,                       NULL,                NULL,                 NULL,                               0)
) AS src (FieldTypeId, FieldType, ExternalTableName, ExternalSearchColumn, ExternalIdColumn, ExternalWhereClause, ExternalNotifFlag)
ON tgt.FieldTypeId = src.FieldTypeId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (FieldTypeId, FieldType, ExternalTableName, ExternalSearchColumn, ExternalIdColumn, ExternalWhereClause, ExternalNotifFlag)
    VALUES (src.FieldTypeId, src.FieldType, src.ExternalTableName, src.ExternalSearchColumn, src.ExternalIdColumn, src.ExternalWhereClause, src.ExternalNotifFlag);

SET IDENTITY_INSERT DemandForecast.FieldType_tbl OFF;
GO