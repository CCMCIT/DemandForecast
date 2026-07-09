/* =====================================================================
   DemandForecast — idempotent seed of FieldType_tbl.
   Inserts the 7 field types with their exact ids (IDENTITY_INSERT ON) in
   one execution. Safe to re-run: MERGE inserts only the rows that are
   missing (WHEN NOT MATCHED), so existing rows are left untouched.

   Run after DemandForecast_schema.sql.
   ===================================================================== */

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