/* =====================================================================
   DemandForecast — idempotent seed of the gate-activity lookups.

   Kept separate from DemandForecast_seed.sql so the gate-activity feature's
   reference data is self-contained. Seeds:
     - FileType_tbl        row 4 (Gate Activities) only; 1-3 are in the main seed
     - GateType            1 = In Gate, 2 = Out Gate
     - LengthMatch_tbl     how EquipLength was determined (1-4)

   Ids mirror src/app/lookups.py. Safe to re-run (MERGE inserts only missing
   rows). Run after DemandForecast_schema.sql + DemandForecast_GateActivity_schema.sql.
   ===================================================================== */

/* ---------- FileType_tbl (Gate Activities) ---------- */

SET IDENTITY_INSERT DemandForecast.FileType_tbl ON;

MERGE DemandForecast.FileType_tbl AS tgt
USING (VALUES
    (4, N'Gate Activities')
) AS src (FileTypeId, Name)
ON tgt.FileTypeId = src.FileTypeId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (FileTypeId, Name)
    VALUES (src.FileTypeId, src.Name);

SET IDENTITY_INSERT DemandForecast.FileType_tbl OFF;
GO

/* ---------- GateType ---------- */

SET IDENTITY_INSERT DemandForecast.GateType_tbl ON;

MERGE DemandForecast.GateType_tbl AS tgt
USING (VALUES
    (1, N'In Gate'),
    (2, N'Out Gate')
) AS src (GateTypeId, Name)
ON tgt.GateTypeId = src.GateTypeId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (GateTypeId, Name)
    VALUES (src.GateTypeId, src.Name);

SET IDENTITY_INSERT DemandForecast.GateType_tbl OFF;
GO

/* ---------- LengthMatch_tbl ----------
   How a row's EquipLength was determined (GateActivityDetail.LengthMatchId). */

SET IDENTITY_INSERT DemandForecast.LengthMatch_tbl ON;

MERGE DemandForecast.LengthMatch_tbl AS tgt
USING (VALUES
    (1, N'Chassis',    N'Length taken from the chassis.'),
    (2, N'ISO Code',   N'Extendible chassis - length derived from the container ISO code.'),
    (3, N'Prior Move', N'Length from the container''s most recent non-extendible move.'),
    (4, N'Default',    N'Fallback default of 45 ft.')
) AS src (LengthMatchId, Name, Description)
ON tgt.LengthMatchId = src.LengthMatchId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (LengthMatchId, Name, Description)
    VALUES (src.LengthMatchId, src.Name, src.Description);

SET IDENTITY_INSERT DemandForecast.LengthMatch_tbl OFF;
GO