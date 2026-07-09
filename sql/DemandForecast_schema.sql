/* =====================================================================
   DemandForecast — idempotent schema (reflected from the live DB).
   Run once to create every table; safe to re-run (each object is guarded
   with IF OBJECT_ID(...) IS NULL). Run in SSMS / sqlcmd (uses GO batches).

   Voyage_tbl and VoyageDetails_tbl are SYSTEM-VERSIONED (temporal); their
   history tables (VoyageHistory_tbl / VoyageDetailsHistory_tbl) are created
   automatically by SQL Server via the WITH (SYSTEM_VERSIONING = ON ...) clause.

   Tables are created in FK-dependency order.
   ===================================================================== */

IF SCHEMA_ID('DemandForecast') IS NULL
    EXEC('CREATE SCHEMA DemandForecast');
GO

/* ---------- Lookups (no FKs) ---------- */

IF OBJECT_ID('DemandForecast.FileType_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.FileType_tbl (
        FileTypeId int IDENTITY(1,1) NOT NULL,
        Name       nvarchar(100) NULL,
        CONSTRAINT PK_FileType PRIMARY KEY (FileTypeId)
    );
GO

IF OBJECT_ID('DemandForecast.LoadStatus_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.LoadStatus_tbl (
        LoadStatusId int IDENTITY(1,1) NOT NULL,
        Name         nvarchar(100) NULL,
        CONSTRAINT PK_LoadStatus PRIMARY KEY (LoadStatusId)
    );
GO

IF OBJECT_ID('DemandForecast.VoyageStatus_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.VoyageStatus_tbl (
        VoyageStatusId   int IDENTITY(1,1) NOT NULL,
        VoyageStatusName nvarchar(100) NULL,
        Description      nvarchar(255) NULL,
        CONSTRAINT PK_VoyageStatus_tbl PRIMARY KEY (VoyageStatusId)
    );
GO

IF OBJECT_ID('DemandForecast.Mode_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.Mode_tbl (
        ModeId      int IDENTITY(1,1) NOT NULL,
        ModeName    nvarchar(100) NULL,
        Description nvarchar(255) NULL,
        CONSTRAINT PK_Mode PRIMARY KEY (ModeId)
    );
GO

IF OBJECT_ID('DemandForecast.Direction_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.Direction_tbl (
        DirectionId   int IDENTITY(1,1) NOT NULL,
        DirectionName nvarchar(100) NULL,
        CONSTRAINT PK_Direction PRIMARY KEY (DirectionId)
    );
GO

IF OBJECT_ID('DemandForecast.FieldType_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.FieldType_tbl (
        FieldTypeId          int IDENTITY(1,1) NOT NULL,
        FieldType            nvarchar(100) NULL,
        ExternalTableName    nvarchar(128) NULL,
        ExternalSearchColumn nvarchar(max) NULL,
        ExternalIdColumn     nvarchar(max) NULL,
        ExternalWhereClause  nvarchar(max) NULL,
        ExternalNotifFlag    bit NOT NULL CONSTRAINT DF_FieldType_ExternalNotifFlag DEFAULT ((0)),
        CONSTRAINT PK_FieldType PRIMARY KEY (FieldTypeId)
    );
GO

IF OBJECT_ID('DemandForecast.FieldValue_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.FieldValue_tbl (
        FieldValueId int IDENTITY(1,1) NOT NULL,
        FieldValue   nvarchar(255) NULL,
        CONSTRAINT PK_FieldValue PRIMARY KEY (FieldValueId)
    );
GO

/* ---------- File + raw detail ---------- */

IF OBJECT_ID('DemandForecast.File_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.File_tbl (
        FileId       int IDENTITY(1,1) NOT NULL,
        FileName     nvarchar(255) NULL,
        DateLoaded   datetime2(0) NOT NULL CONSTRAINT DF_File_DateLoaded DEFAULT (getdate()),
        FileTypeId   int NULL,
        LoadStatusId int NULL,
        CONSTRAINT PK_File PRIMARY KEY (FileId),
        CONSTRAINT FK_File_FileType   FOREIGN KEY (FileTypeId)   REFERENCES DemandForecast.FileType_tbl (FileTypeId),
        CONSTRAINT FK_File_LoadStatus FOREIGN KEY (LoadStatusId) REFERENCES DemandForecast.LoadStatus_tbl (LoadStatusId)
    );
GO

IF OBJECT_ID('DemandForecast.GpaFileDetail_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.GpaFileDetail_tbl (
        FileDetailId int IDENTITY(1,1) NOT NULL,
        FileId       int NOT NULL,
        TERMINAL     nvarchar(100) NULL,
        WORK_DATE    date NULL,
        VESSEL       nvarchar(100) NULL,
        VOYAGE       nvarchar(100) NULL,
        LINE         nvarchar(100) NULL,
        SERVICE      nvarchar(100) NULL,
        FROM_PORT    nvarchar(100) NULL,
        TO_PORT      nvarchar(100) NULL,
        WORKTIME     time(0) NULL,
        IM_FULL20    int NULL,
        IM_FULL40    int NULL,
        IM_FULL45    int NULL,
        IM_MT        int NULL,
        EX_FULL20    int NULL,
        EX_FULL40    int NULL,
        EX_MT        int NULL,
        TOTAL        int NULL,
        RAIL_IM20    int NULL,
        RAIL_IM40    int NULL,
        REPORTED     nvarchar(50) NULL,
        CONSTRAINT PK_GpaFileDetail PRIMARY KEY (FileDetailId),
        CONSTRAINT FK_GpaFileDetail_File FOREIGN KEY (FileId) REFERENCES DemandForecast.File_tbl (FileId)
    );
GO

/* ---------- Field mapping dimension ---------- */

IF OBJECT_ID('DemandForecast.FieldTypeValue_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.FieldTypeValue_tbl (
        FieldTypeValueId  int IDENTITY(1,1) NOT NULL,
        FieldTypeId       int NOT NULL,
        FieldValueId      int NOT NULL,
        ExternalId        int NULL,
        ExternalNotifFlag bit NULL,
        CONSTRAINT PK_FieldTypeValue PRIMARY KEY (FieldTypeValueId),
        CONSTRAINT FK_FieldTypeValue_FieldType  FOREIGN KEY (FieldTypeId)  REFERENCES DemandForecast.FieldType_tbl (FieldTypeId),
        CONSTRAINT FK_FieldTypeValue_FieldValue FOREIGN KEY (FieldValueId) REFERENCES DemandForecast.FieldValue_tbl (FieldValueId)
    );
GO

/* ---------- Voyage + details (SYSTEM-VERSIONED / temporal) ----------
   The history tables are auto-created by SQL Server from the WITH clause. */

IF OBJECT_ID('DemandForecast.Voyage_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.Voyage_tbl (
        VoyageId       int IDENTITY(1,1) NOT NULL,
        FileId         int NOT NULL,
        Voyage         nvarchar(100) NOT NULL,
        WORK_DATE      date NULL,
        WorkTime       time(0) NULL,
        VoyageStatusId int NOT NULL CONSTRAINT DF_Voyage_VoyageStatusId DEFAULT ((1)),
        SysStartTime   datetime2(7) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        SysEndTime     datetime2(7) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_Voyage PRIMARY KEY (VoyageId),
        CONSTRAINT UQ_Voyage_Voyage UNIQUE (Voyage),
        CONSTRAINT FK_Voyage_File FOREIGN KEY (FileId) REFERENCES DemandForecast.File_tbl (FileId),
        PERIOD FOR SYSTEM_TIME (SysStartTime, SysEndTime)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.VoyageHistory_tbl));
GO

IF OBJECT_ID('DemandForecast.VoyageDetails_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.VoyageDetails_tbl (
        VoyageDetailsId           int IDENTITY(1,1) NOT NULL,
        VoyageId                  int NOT NULL,
        FieldTypeValueEquipTypeId int NULL,
        ModeId                    int NULL,
        DirectionId               int NULL,
        ContainerLoadedFlag       bit NULL,
        Containers                int NULL,
        SysStartTime              datetime2(7) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL,
        SysEndTime                datetime2(7) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL,
        CONSTRAINT PK_VoyageDetails PRIMARY KEY (VoyageDetailsId),
        CONSTRAINT FK_VoyageDetails_Voyage         FOREIGN KEY (VoyageId)                  REFERENCES DemandForecast.Voyage_tbl (VoyageId),
        CONSTRAINT FK_VoyageDetails_Mode           FOREIGN KEY (ModeId)                    REFERENCES DemandForecast.Mode_tbl (ModeId),
        CONSTRAINT FK_VoyageDetails_Direction      FOREIGN KEY (DirectionId)               REFERENCES DemandForecast.Direction_tbl (DirectionId),
        CONSTRAINT FK_VoyageDetails_FieldTypeValue FOREIGN KEY (FieldTypeValueEquipTypeId) REFERENCES DemandForecast.FieldTypeValue_tbl (FieldTypeValueId),
        PERIOD FOR SYSTEM_TIME (SysStartTime, SysEndTime)
    )
    WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = DemandForecast.VoyageDetailsHistory_tbl));
GO

/* ---------- Voyage <-> field-value map ---------- */

IF OBJECT_ID('DemandForecast.VoyageFieldMap_tbl', 'U') IS NULL
    CREATE TABLE DemandForecast.VoyageFieldMap_tbl (
        MapId            int IDENTITY(1,1) NOT NULL,
        VoyageId         int NOT NULL,
        FieldTypeValueId int NOT NULL,
        CONSTRAINT PK_VoyageFieldMap PRIMARY KEY (MapId),
        CONSTRAINT FK_VoyageFieldMap_Voyage         FOREIGN KEY (VoyageId)         REFERENCES DemandForecast.Voyage_tbl (VoyageId),
        CONSTRAINT FK_VoyageFieldMap_FieldTypeValue FOREIGN KEY (FieldTypeValueId) REFERENCES DemandForecast.FieldTypeValue_tbl (FieldTypeValueId)
    );
GO