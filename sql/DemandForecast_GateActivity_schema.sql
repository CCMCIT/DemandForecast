/* =====================================================================
   DemandForecast — Gate Activity schema

   Captures the gate-activity tables as they exist in the live DB, in the
   same idempotent style as DemandForecast_schema.sql (create only if
   absent; the app never alters tables at runtime).

     - GateType                        lookup (1 = In Gate, 2 = Out Gate)
     - LengthMatch_tbl                 lookup: how EquipLength was determined
     - CmsGateActivityDetail_tbl       CMS raw staging (one row per file row)
     - GateActivityDetail_tbl          processed target, SYSTEM-VERSIONED

   The target's IDENTITY is the 10 columns of UQ_GateActivityDetail_Identity
   (Date + the nine dimension columns). Processing upserts on that identity;
   an UPDATE archives the prior row version into GateActivityDetailHistory_tbl.

   DRIFT NOTE: the live tables currently carry NO foreign keys. The voyage
   tables constrain LoadId -> Load_tbl (and VoyageDetails -> FieldTypeValue);
   gate activity does not. This script reflects the live state (no FKs). To
   restore referential integrity, add the FKs listed at the bottom.
   ===================================================================== */
GO

/* ---------- GateType (lookup) ---------- */

IF OBJECT_ID('DemandForecast.GateType_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.GateType_tbl (
        GateTypeId int IDENTITY(1,1) NOT NULL,
        Name       nvarchar(50) NOT NULL,
        CONSTRAINT PK_GateType PRIMARY KEY (GateTypeId)
    );
GO

/* ---------- LengthMatch (lookup) ----------
   How a row's EquipLength was determined; GateActivityDetail.LengthMatchId
   references this. Columns assumed (LengthMatchId, Name, Description) --
   adjust if the live table differs. */

IF OBJECT_ID('DemandForecast.LengthMatch_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.LengthMatch_tbl (
        LengthMatchId int IDENTITY(1,1) NOT NULL,
        Name          nvarchar(50) NOT NULL,
        Description   nvarchar(255) NULL,
        CONSTRAINT PK_LengthMatch PRIMARY KEY (LengthMatchId)
    );
GO

/* ---------- CMS raw staging ---------- */

IF OBJECT_ID('DemandForecast.CmsGateActivityDetail_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.CmsGateActivityDetail_tbl (
        CmsGateActivityDetailId int IDENTITY(1,1) NOT NULL,
        LoadId              int NOT NULL,
        Date                date NOT NULL,
        TruckerName         nvarchar(200) NULL,
        EquipCode           nvarchar(50) NULL,
        EquipLength         int NULL,
        LengthMatchId       int NULL,
        OceanCarrierName    nvarchar(200) NULL,
        GateType            nvarchar(100) NULL,
        BareChassisFlag     bit NULL,
        ContainerLoadedFlag bit NULL,
        LocationName        nvarchar(200) NULL,
        Units               int NULL,
        Transactions        int NULL,
        CONSTRAINT PK_CmsGateActivityDetail PRIMARY KEY (CmsGateActivityDetailId)
    );
GO

/* ---------- Processed target (SYSTEM-VERSIONED / temporal) ----------
   The history table is auto-created by SQL Server from the WITH clause.
   UQ_GateActivityDetail_Identity makes each (Date + dimensions) unique, so
   processing can upsert-by-identity. NULLs are treated as equal, so a row
   with a NULL dimension still collapses to one live row. */

IF OBJECT_ID('DemandForecast.GateActivityDetail_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.GateActivityDetail_tbl (
        GateActivityDetailId         int IDENTITY(1,1) NOT NULL,
        LoadId                       int NOT NULL,
        Date                         date NOT NULL,
        FieldTypeValueTruckerId      int NULL,
        FieldTypeValueEquipTypeId    int NULL,
        EquipLength                  int NULL,
        LengthMatchId                int NULL,
        FieldTypeValueOceanCarrierId int NULL,
        GateTypeId                   int NULL,
        BareChassisFlag              bit NULL,
        ContainerLoadedFlag          bit NULL,
        FieldTypeValueLocationId     int NULL,
        Units                        int NULL,
        Transactions                 int NULL,
        SysStartTime  datetime2(7) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        SysEndTime    datetime2(7) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_GateActivityDetail PRIMARY KEY (GateActivityDetailId),
        CONSTRAINT UQ_GateActivityDetail_Identity UNIQUE (
            Date,
            FieldTypeValueTruckerId,
            FieldTypeValueEquipTypeId,
            EquipLength,
            LengthMatchId,
            FieldTypeValueOceanCarrierId,
            GateTypeId,
            BareChassisFlag,
            ContainerLoadedFlag,
            FieldTypeValueLocationId
        ),
        PERIOD FOR SYSTEM_TIME (SysStartTime, SysEndTime)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.GateActivityDetailHistory_tbl));
GO

/* ---------- Optional: restore referential integrity (drift) ----------
   The live tables have no FKs; run these to match the voyage-table pattern.

   ALTER TABLE DemandForecast.CmsGateActivityDetail_tbl
       ADD CONSTRAINT FK_CmsGateActivityDetail_File
       FOREIGN KEY (LoadId) REFERENCES DemandForecast.Load_tbl (LoadId);

   ALTER TABLE DemandForecast.GateActivityDetail_tbl
       ADD CONSTRAINT FK_GateActivityDetail_File
       FOREIGN KEY (LoadId) REFERENCES DemandForecast.Load_tbl (LoadId);
   -- (GateTypeId / FieldTypeValue* columns are left unconstrained, matching live.)
*/

/* LengthMatchId -> LengthMatch_tbl (being added). Run once LengthMatch_tbl exists
   and every LengthMatchId in the tables is 1-4 or NULL:

   ALTER TABLE DemandForecast.GateActivityDetail_tbl
       ADD CONSTRAINT FK_GateActivityDetail_LengthMatch
       FOREIGN KEY (LengthMatchId) REFERENCES DemandForecast.LengthMatch_tbl (LengthMatchId);

   ALTER TABLE DemandForecast.CmsGateActivityDetail_tbl
       ADD CONSTRAINT FK_CmsGateActivityDetail_LengthMatch
       FOREIGN KEY (LengthMatchId) REFERENCES DemandForecast.LengthMatch_tbl (LengthMatchId);
*/