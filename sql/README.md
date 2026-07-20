# SQL scripts

The database owns the schema. These scripts create the tables/lookups/procs; the app
never alters tables. All are idempotent (`IF OBJECT_ID` / `MERGE` / `CREATE OR ALTER`).

## Fresh environment — run in order

```
1. DemandForecast_schema.sql
2. DemandForecast_GateActivity_schema.sql
3. DemandForecast_seed.sql
4. DemandForecast_GateActivity_seed.sql
5. DemandForecast_FTV_procs.sql
6. DemandForecast_GateActivity_procs.sql
```

Schema before seed; procs need only the tables. Fresh builds already use the new names
(`Load_tbl`, `LoadType_tbl`) — no migration needed.

## Existing environment — rename to the new names

Run `rename_File_to_Load.sql` (STEP 0 review → STEP 1 rename → STEP 2 verify), once per
environment.

⚠ On an environment without gate activity (e.g. UAT), STEP 1's two gate-activity table
renames must be guarded, or the whole transaction aborts:

```sql
IF COL_LENGTH('DemandForecast.CmsGateActivityDetail_naum_tbl', 'FileId') IS NOT NULL
    EXEC sp_rename 'DemandForecast.CmsGateActivityDetail_naum_tbl.FileId', 'LoadId', 'COLUMN';
IF COL_LENGTH('DemandForecast.GateActivityDetail_tbl', 'FileId') IS NOT NULL
    EXEC sp_rename 'DemandForecast.GateActivityDetail_tbl.FileId', 'LoadId', 'COLUMN';
```

To add gate activity later, run scripts 2, 4, 6 — they already use the new names.

## Utility

`reset_voyage_data.sql` — **destructive**, wipes all voyage + history rows. Back up first.