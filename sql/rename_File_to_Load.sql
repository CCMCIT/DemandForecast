/* =====================================================================
   One-off migration: rename File_tbl -> Load_tbl and its columns.

   Applies to the DemandForecast schema:
     GateType                -> GateType_tbl      (guarded; skipped if already done)
     File_tbl                -> Load_tbl
     File_tbl.FileId         -> LoadId          (+ every FileId FK column below)
     File_tbl.FileName       -> SourceName
     File_tbl.FileTypeId     -> LoadTypeId
     FileType_tbl.FileTypeId -> LoadTypeId       (lookup PK; table name unchanged)

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

-- FileType_tbl lookup: rename only its PK column (table name stays FileType_tbl).
EXEC sp_rename 'DemandForecast.FileType_tbl.FileTypeId', 'LoadTypeId', 'COLUMN';

-- The File table's own columns (rename columns first, table last).
EXEC sp_rename 'DemandForecast.File_tbl.FileId',     'LoadId',     'COLUMN';
EXEC sp_rename 'DemandForecast.File_tbl.FileName',   'SourceName', 'COLUMN';
EXEC sp_rename 'DemandForecast.File_tbl.FileTypeId', 'LoadTypeId', 'COLUMN';

-- The FileId foreign-key columns on every child table -> LoadId.
EXEC sp_rename 'DemandForecast.GpaFileDetail_tbl.FileId',              'LoadId', 'COLUMN';
EXEC sp_rename 'DemandForecast.Voyage_tbl.FileId',                     'LoadId', 'COLUMN';  -- temporal -> VoyageHistory_tbl
EXEC sp_rename 'DemandForecast.CmsGateActivityDetail_naum_tbl.FileId', 'LoadId', 'COLUMN';
EXEC sp_rename 'DemandForecast.GateActivityDetail_tbl.FileId',         'LoadId', 'COLUMN';  -- temporal -> GateActivityDetailHistory_tbl

-- Finally, the table itself.
EXEC sp_rename 'DemandForecast.File_tbl', 'Load_tbl';

COMMIT;
GO

/* ---------- STEP 2: verify ----------
   Expect: LoadId, SourceName, DateLoaded, LoadTypeId, LoadStatusId */
SELECT name FROM sys.columns
WHERE object_id = OBJECT_ID('DemandForecast.Load_tbl')
ORDER BY column_id;
GO
