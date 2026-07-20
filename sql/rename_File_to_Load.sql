/* =====================================================================
   One-off migration: rename File_tbl -> Load_tbl and its columns.

   Applies to the DemandForecast schema:
     GateType                -> GateType_tbl      (guarded; skipped if already done)
     File_tbl                -> Load_tbl
     File_tbl.FileId         -> LoadId          (+ every FileId FK column below)
     File_tbl.FileName       -> SourceName
     File_tbl.FileTypeId     -> LoadTypeId
     FileType_tbl            -> LoadType_tbl      (the load-type lookup table)
     FileType_tbl.FileTypeId -> LoadTypeId       (its PK column)
     LoadStatus_tbl labels   -> ids 1-4 row values (data, not a schema change):
                                 1 File       -> Load
                                 2 FileDetail -> LoadDetail
                                 3 Voyage     -> Header
                                 4 VoyageDetail -> Detail

   HOW TO RUN
     1. Pick the target database (USE <db>, or select it in SSMS).
     2. Run STEP 0 first and read its result set: it lists any view/proc/
        function that mentions the old names. Those are NOT auto-fixed --
        update them after the rename (the columns still exist, just renamed).
     3. Run STEP 1 (the rename). It is one transaction; any error rolls it
        all back.
     4. Run STEP 2 to verify.
     5. Repeat for each environment you want migrated (dev, then uat, prod).

   Voyage_tbl and GateActivityDetail_tbl are system-versioned: sp_rename of a
   column propagates automatically to their history tables, so they are NOT
   renamed here. Constraint names (PK_File, FK_File_*, DF_File_DateLoaded, ...)
   are left as-is; sp_rename never touches them.
   ===================================================================== */

-- USE <your_database>;   -- uncomment and set, or pick the DB in SSMS first
-- GO

/* ---------- STEP 0: pre-flight. Objects that reference the old names ----------
   Review the rows this returns. Any view/proc/function listed still hard-codes
   an old name and must be edited after STEP 1 (this query changes nothing). */
SELECT OBJECT_SCHEMA_NAME(m.object_id) AS sch,
       OBJECT_NAME(m.object_id)        AS obj,
       o.type_desc
FROM sys.sql_modules m
JOIN sys.objects o ON o.object_id = m.object_id
WHERE m.definition LIKE '%File_tbl%'
   OR m.definition LIKE '%FileType_tbl%'
   OR m.definition LIKE '%FileId%'
   OR m.definition LIKE '%FileName%'
   OR m.definition LIKE '%FileTypeId%';
GO

/* ---------- STEP 1: the rename (one transaction) ---------- */
SET XACT_ABORT ON;   -- any error rolls the whole batch back
BEGIN TRAN;

-- GateType -> GateType_tbl (earlier rename; guarded so it is safe to run on an
-- environment where it was already applied).
IF OBJECT_ID('DemandForecast.GateType', 'U') IS NOT NULL
    EXEC sp_rename 'DemandForecast.GateType', 'GateType_tbl';

-- FileType_tbl lookup -> LoadType_tbl: rename its PK column, then the table.
-- Guarded so it is safe to re-run and safe on an environment where an earlier
-- version of this script already renamed the column but not the table.
IF OBJECT_ID('DemandForecast.FileType_tbl', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('DemandForecast.FileType_tbl', 'FileTypeId') IS NOT NULL
        EXEC sp_rename 'DemandForecast.FileType_tbl.FileTypeId', 'LoadTypeId', 'COLUMN';
    EXEC sp_rename 'DemandForecast.FileType_tbl', 'LoadType_tbl';
END

-- The File table's own columns (rename columns first, table last). Each guarded
-- by COL_LENGTH so a re-run skips already-renamed columns instead of aborting.
IF COL_LENGTH('DemandForecast.File_tbl', 'FileId') IS NOT NULL
    EXEC sp_rename 'DemandForecast.File_tbl.FileId', 'LoadId', 'COLUMN';
IF COL_LENGTH('DemandForecast.File_tbl', 'FileName') IS NOT NULL
    EXEC sp_rename 'DemandForecast.File_tbl.FileName', 'SourceName', 'COLUMN';
IF COL_LENGTH('DemandForecast.File_tbl', 'FileTypeId') IS NOT NULL
    EXEC sp_rename 'DemandForecast.File_tbl.FileTypeId', 'LoadTypeId', 'COLUMN';

-- The FileId foreign-key columns on every child table -> LoadId.
IF COL_LENGTH('DemandForecast.GpaFileDetail_tbl', 'FileId') IS NOT NULL
    EXEC sp_rename 'DemandForecast.GpaFileDetail_tbl.FileId', 'LoadId', 'COLUMN';
IF COL_LENGTH('DemandForecast.Voyage_tbl', 'FileId') IS NOT NULL
    EXEC sp_rename 'DemandForecast.Voyage_tbl.FileId', 'LoadId', 'COLUMN';  -- temporal -> VoyageHistory_tbl
-- Guarded: these tables are absent on GPA-only envs (e.g. UAT). COL_LENGTH is
-- NULL when the table/column is missing, so the rename skips instead of aborting.
IF COL_LENGTH('DemandForecast.CmsGateActivityDetail_naum_tbl', 'FileId') IS NOT NULL
    EXEC sp_rename 'DemandForecast.CmsGateActivityDetail_naum_tbl.FileId', 'LoadId', 'COLUMN';
IF COL_LENGTH('DemandForecast.GateActivityDetail_tbl', 'FileId') IS NOT NULL
    EXEC sp_rename 'DemandForecast.GateActivityDetail_tbl.FileId', 'LoadId', 'COLUMN';  -- temporal -> GateActivityDetailHistory_tbl

-- Finally, the table itself (guarded: skipped once already renamed to Load_tbl).
IF OBJECT_ID('DemandForecast.File_tbl', 'U') IS NOT NULL
    EXEC sp_rename 'DemandForecast.File_tbl', 'Load_tbl';

-- LoadStatus_tbl row labels (ids 1-4): File/FileDetail/Voyage/VoyageDetail ->
-- Load/LoadDetail/Header/Detail. Data only (not schema); each is guarded by the
-- old value so it is a no-op once already renamed.
UPDATE DemandForecast.LoadStatus_tbl
   SET Name = N'Inserted into Load'
 WHERE LoadStatusId = 1 AND Name = N'Inserted into File';

UPDATE DemandForecast.LoadStatus_tbl
   SET Name = N'Inserted into LoadDetail'
 WHERE LoadStatusId = 2 AND Name = N'Inserted into FileDetail';

UPDATE DemandForecast.LoadStatus_tbl
   SET Name = N'Inserted into Header'
 WHERE LoadStatusId = 3 AND Name = N'Inserted into Voyage';

UPDATE DemandForecast.LoadStatus_tbl
   SET Name = N'Inserted into Detail'
 WHERE LoadStatusId = 4 AND Name = N'Inserted into VoyageDetail';

COMMIT;
GO

/* ---------- STEP 2: verify ----------
   Expect: LoadId, SourceName, DateLoaded, LoadTypeId, LoadStatusId */
SELECT name FROM sys.columns
WHERE object_id = OBJECT_ID('DemandForecast.Load_tbl')
ORDER BY column_id;
GO

/* LoadType_tbl should now exist (renamed from FileType_tbl) with PK column
   LoadTypeId. Expect: LoadTypeId, Name */
SELECT name FROM sys.columns
WHERE object_id = OBJECT_ID('DemandForecast.LoadType_tbl')
ORDER BY column_id;
GO
