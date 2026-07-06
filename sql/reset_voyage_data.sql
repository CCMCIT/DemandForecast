/* ============================================================================
   reset_voyage_data.sql

   Deletes ALL rows from these four tables:
       DemandForecast.Voyage_tbl
       DemandForecast.VoyageDetails_tbl
       DemandForecast.VoyageHistory_tbl
       DemandForecast.VoyageDetailsHistory_tbl

   It does this by turning SYSTEM_VERSIONING OFF, deleting from all four, then
   turning it back ON against the same history tables.

   Each stage is its own batch (separated by GO) so the OFF fully takes effect
   before the deletes run -- otherwise SQL Server still treats the history
   tables as protected and raises "Cannot delete rows from a temporal history
   table" (error 13560).

   ----------------------------------------------------------------------------
   !! DESTRUCTIVE AND IRREVERSIBLE !!
     - Take a database backup first if there is any chance you need this data.
     - Run against the CORRECT database (this file targets CMSystemScripts).
     - Run the WHOLE file (F5), not a selection -- each stage is a batch.
     - Run while the pipeline is NOT ingesting/processing.
   ----------------------------------------------------------------------------
   If anything aborts mid-way, see "MANUAL RESTORE" at the bottom of this file.
   ============================================================================ */

SET XACT_ABORT ON;
SET NOCOUNT ON;
GO

USE [CMSystemScripts];
GO

/* ---- 1. Turn system-versioning OFF (decouples current + history) ---- */
ALTER TABLE DemandForecast.Voyage_tbl        SET (SYSTEM_VERSIONING = OFF);
ALTER TABLE DemandForecast.VoyageDetails_tbl SET (SYSTEM_VERSIONING = OFF);
GO

/* ---- 2. Delete from all four tables.
          Current tables: child (VoyageDetails) before parent (Voyage) for the FK.
          History tables: plain tables now that versioning is off. ---- */
DELETE FROM DemandForecast.VoyageDetailsHistory_tbl;
DELETE FROM DemandForecast.VoyageHistory_tbl;
DELETE FROM DemandForecast.VoyageDetails_tbl;
DELETE FROM DemandForecast.Voyage_tbl;
GO

/* ---- 3. Re-enable system-versioning against the SAME history tables.
          DATA_CONSISTENCY_CHECK validates the period columns (trivially passes
          now that both current and history are empty). ---- */
ALTER TABLE DemandForecast.Voyage_tbl
    SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.VoyageHistory_tbl, DATA_CONSISTENCY_CHECK = ON));
ALTER TABLE DemandForecast.VoyageDetails_tbl
    SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.VoyageDetailsHistory_tbl, DATA_CONSISTENCY_CHECK = ON));
GO

/* ---- 4. Reset identity so the next insert starts at 1.
          RESEED to 0 -> next inserted value = 0 + 1 = 1. Only the current tables
          have an identity column (VoyageId, VoyageDetailsId). ---- */
DBCC CHECKIDENT ('DemandForecast.Voyage_tbl',        RESEED, 0);
DBCC CHECKIDENT ('DemandForecast.VoyageDetails_tbl', RESEED, 0);
GO

/* ---- 5. Verify: all four counts should be 0, both tables versioned again ---- */
SELECT 'Voyage_tbl'               AS TableName, COUNT(*) AS [Rows] FROM DemandForecast.Voyage_tbl
UNION ALL SELECT 'VoyageDetails_tbl',        COUNT(*) FROM DemandForecast.VoyageDetails_tbl
UNION ALL SELECT 'VoyageHistory_tbl',        COUNT(*) FROM DemandForecast.VoyageHistory_tbl
UNION ALL SELECT 'VoyageDetailsHistory_tbl', COUNT(*) FROM DemandForecast.VoyageDetailsHistory_tbl;

/* Identity should read 0 now, so the next insert becomes 1. */
SELECT 'Voyage_tbl'        AS TableName, IDENT_CURRENT('DemandForecast.Voyage_tbl')        AS CurrentIdentity
UNION ALL
SELECT 'VoyageDetails_tbl',              IDENT_CURRENT('DemandForecast.VoyageDetails_tbl');

SELECT
    SCHEMA_NAME(t.schema_id) AS TableSchema,
    t.name                   AS CurrentTable,
    t.temporal_type_desc,
    SCHEMA_NAME(h.schema_id) AS HistorySchema,
    h.name                   AS HistoryTable
FROM sys.tables t
LEFT JOIN sys.tables h ON t.history_table_id = h.object_id
WHERE SCHEMA_NAME(t.schema_id) = 'DemandForecast'
  AND t.name IN ('Voyage_tbl', 'VoyageDetails_tbl');
GO

/* ============================================================================
   MANUAL RESTORE (only if the script aborted after stage 1 and left a table
   with SYSTEM_VERSIONING = OFF). Run:

     ALTER TABLE DemandForecast.Voyage_tbl
       SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.VoyageHistory_tbl,        DATA_CONSISTENCY_CHECK = ON));
     ALTER TABLE DemandForecast.VoyageDetails_tbl
       SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.VoyageDetailsHistory_tbl, DATA_CONSISTENCY_CHECK = ON));
   ============================================================================ */