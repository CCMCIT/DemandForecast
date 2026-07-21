# SQL scripts

The database owns the schema. These scripts create the tables/lookups/procs; the app
never alters tables. All are idempotent (`IF OBJECT_ID` / `MERGE` / `CREATE OR ALTER`).

## Fresh environment — run in order

```
1. DemandForecast_schema.sql
2. DemandForecast_GateActivity_schema.sql
3. DemandForecast_OnTerm_schema.sql
4. DemandForecast_seed.sql
5. DemandForecast_GateActivity_seed.sql
6. DemandForecast_OnTerm_seed.sql
7. DemandForecast_FTV_procs.sql
8. DemandForecast_GateActivity_procs.sql
```

Schema before seed; procs need only the tables. Fresh builds already use the new names
(`Load_tbl`, `LoadType_tbl`) — no migration needed.

`DemandForecast_OnTerm_schema.sql` (3) creates the on-terminal tables (`CmsOnTermDetail_tbl`
and the system-versioned `OnTermDetail_tbl`); `DemandForecast_OnTerm_seed.sql` (6) seeds
`LoadType_tbl` row 5 (`On Terminal`). On-terminal reuses `GateActivityFieldTypeValue_upsert`
(script 8) — no new proc.

## Existing environment — rename to the new names

Run `rename_File_to_Load.sql` (STEP 0 review → STEP 1 rename → STEP 2 verify), once per
environment.

⚠ On an environment without gate activity (e.g. UAT), STEP 1's two gate-activity table
renames must be guarded, or the whole transaction aborts:

```sql
IF COL_LENGTH('DemandForecast.CmsGateActivityDetail_tbl', 'FileId') IS NOT NULL
    EXEC sp_rename 'DemandForecast.CmsGateActivityDetail_tbl.FileId', 'LoadId', 'COLUMN';
IF COL_LENGTH('DemandForecast.GateActivityDetail_tbl', 'FileId') IS NOT NULL
    EXEC sp_rename 'DemandForecast.GateActivityDetail_tbl.FileId', 'LoadId', 'COLUMN';
```

To add gate activity later, run scripts 2, 5, 8 — they already use the new names. To add
on terminal later, run scripts 3, 6, 8 (its field-value proc is the shared gate-activity
proc, script 8).

## Utility

`reset_voyage_data.sql` — **destructive**, wipes all voyage + history rows. Back up first.