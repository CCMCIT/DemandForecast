/* =====================================================================
   DemandForecast — idempotent seed of the on-terminal lookups.

   Kept separate from DemandForecast_seed.sql so the on-terminal feature's
   reference data is self-contained (like the gate-activity seed). Seeds:
     - LoadType_tbl        row 5 (On Terminal) only; 1-3 are in the main seed,
                           4 (Gate Activities) is in the gate-activity seed

   On terminal has no lookups of its own (Equipment/Location resolve to
   FieldTypeValue rows via the shared proc), so this is the only row it needs.

   Id mirrors src/app/lookups.py (FileType.ON_TERMINAL = 5). Safe to re-run
   (MERGE inserts only the missing row; does nothing if it already exists).
   Run after DemandForecast_schema.sql + DemandForecast_OnTerm_schema.sql.
   ===================================================================== */

/* ---------- LoadType_tbl (On Terminal) ---------- */

SET IDENTITY_INSERT DemandForecast.LoadType_tbl ON;

MERGE DemandForecast.LoadType_tbl AS tgt
USING (VALUES
    (5, N'On Terminal')
) AS src (LoadTypeId, Name)
ON tgt.LoadTypeId = src.LoadTypeId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (LoadTypeId, Name)
    VALUES (src.LoadTypeId, src.Name);

SET IDENTITY_INSERT DemandForecast.LoadType_tbl OFF;
GO
