/* =====================================================================
   DemandForecast — On Terminal schema

   Captures the on-terminal tables as they exist in the live DB, in the same
   idempotent style as DemandForecast_GateActivity_schema.sql (create only if
   absent; the app never alters tables at runtime).

     - CmsOnTermDetail_tbl   CMS raw staging (one row per file row)
     - OnTermDetail_tbl      processed target, SYSTEM-VERSIONED

   Processed rows are upserted by identity (Date + the two dimension columns
   FieldTypeValueEquipTypeId / FieldTypeValueLocationId) in the writer; an
   UPDATE archives the prior row version into OnTermDetailHistory_tbl.

   NOTE: on-terminal files are LoadType 5 ('On Terminal'). That LoadType_tbl row
   must be seeded before processing (a fresh environment needs it); it is not
   created here. Field-value resolution reuses DemandForecast.GateActivity-
   FieldTypeValue_upsert, so no on-terminal proc is needed.

   DRIFT NOTE: like the gate-activity tables, these carry NO foreign keys, matching
   the live DB. To add them, run the statements at the bottom.
   ===================================================================== */
GO

/* ---------- CMS raw staging ---------- */

IF OBJECT_ID('DemandForecast.CmsOnTermDetail_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.CmsOnTermDetail_tbl (
        CmsOnTermDetailId int IDENTITY(1,1) NOT NULL,
        LoadId            int NOT NULL,
        Date              date NOT NULL,
        EquipCode         nvarchar(50) NULL,   -- from "Equip Code"
        LocationName      nvarchar(200) NULL,  -- from "Title"
        Units             int NULL,
        CONSTRAINT PK_CmsOnTermDetail PRIMARY KEY (CmsOnTermDetailId)
    );
GO

/* ---------- Processed target (SYSTEM-VERSIONED / temporal) ----------
   The history table is auto-created by SQL Server from the WITH clause. Rows
   are upserted by identity (Date + the two dimension columns); an UPDATE
   archives the prior version into OnTermDetailHistory_tbl. */

IF OBJECT_ID('DemandForecast.OnTermDetail_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.OnTermDetail_tbl (
        OnTermDetailId            int IDENTITY(1,1) NOT NULL,
        LoadId                    int NOT NULL,
        Date                      date NOT NULL,
        FieldTypeValueEquipTypeId int NULL,
        FieldTypeValueLocationId  int NULL,
        Units                     int NULL,
        SysStartTime  datetime2(7) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        SysEndTime    datetime2(7) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_OnTermDetail PRIMARY KEY (OnTermDetailId),
        PERIOD FOR SYSTEM_TIME (SysStartTime, SysEndTime)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.OnTermDetailHistory_tbl));
GO

/* ---------- Unique identity (the upsert key) ----------
   One live row per (Date + the two dimension columns), so the writer's insert-vs-
   update decision is DB-guaranteed: a matching identity UPDATEs in place (temporal
   archives the prior version), a new one INSERTs. NULLs compare equal in a UNIQUE
   constraint, so a row with NULL dimensions still collapses to one live row.
   Idempotent. */

IF NOT EXISTS (
    SELECT 1 FROM sys.objects
    WHERE name = 'UQ_OnTermDetail_Identity'
      AND parent_object_id = OBJECT_ID('DemandForecast.OnTermDetail_tbl')
)
    ALTER TABLE DemandForecast.OnTermDetail_tbl
        ADD CONSTRAINT UQ_OnTermDetail_Identity UNIQUE (
            Date,
            FieldTypeValueEquipTypeId,
            FieldTypeValueLocationId
        );
GO

/* ---------- Optional: restore referential integrity (drift) ----------
   The live tables have no FKs; run these to match the voyage-table pattern.

   ALTER TABLE DemandForecast.CmsOnTermDetail_tbl
       ADD CONSTRAINT FK_CmsOnTermDetail_Load
       FOREIGN KEY (LoadId) REFERENCES DemandForecast.Load_tbl (LoadId);

   ALTER TABLE DemandForecast.OnTermDetail_tbl
       ADD CONSTRAINT FK_OnTermDetail_Load
       FOREIGN KEY (LoadId) REFERENCES DemandForecast.Load_tbl (LoadId);
*/