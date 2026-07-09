# Architecture

Three separate jobs, never merged. Shared targets are agnostic to the source, so
adding a company touches only that company's files.

- **Job 1 — Ingestion:** a file on disk → `File_tbl` + a company detail table
  (e.g. `GpaFileDetail_tbl`).
- **Job 2 — Processing:** the detail table → `Voyage_tbl` + `VoyageDetails_tbl`, plus
  the field-mapping tables (`FieldValue_tbl` → `FieldTypeValue_tbl` → `VoyageFieldMap_tbl`).
- **Job 3 — Forecast:** future; reads via repositories only.

## Database-first rules

- The DB owns the schema. The code **never** creates or alters tables — no
  `CREATE TABLE`, no migrations, no Alembic.
- Models reflect existing tables only. For a new table, reflect it from the live DB;
  never hand-invent columns. If a column name or type is unknown, ask — don't guess.

## Folder structure

```
run.py                          # launcher: python run.py <command> (puts src/ on the path)
src/app/
├── lookups.py                  # FileType / LoadStatus / VoyageStatus / FieldType ids (mirror the DB)
├── config/settings.py          # .env -> Env(dev/uat/prod) + connection_string + paths
├── db/
│   ├── session.py              # engine + SessionLocal; configure(env) binds dev/uat/prod
│   ├── models/                 # reflected models, one per table
│   └── repositories/           # one per table; the ONLY place with DB queries
├── ingestion/                  # JOB 1: file on disk -> raw company table
│   ├── base.py                 #   reader/loader contracts
│   ├── registry.py             #   FileTypeId -> (reader, loader)   <- add a company here
│   ├── runner.py               #   shared flow, one transaction per file
│   └── gpa/                    #   GPA reader + loader (company-specific)
├── processing/                 # JOB 2: raw table -> Voyage + VoyageDetails + field maps
│   ├── dto.py                  #   MappedVoyage / MappedDetail / MappedField (source-agnostic)
│   ├── field_mapping.py        #   build_fields(row, spec) -> MappedField[] (shared)
│   ├── validation.py           #   prevalidation: VOYAGE + WORK_DATE required
│   ├── writer.py               #   VoyageWriter: writes voyages/details; field maps via proc
│   ├── status.py               #   fallen-off classification (Called / Canceled)
│   ├── registry.py             #   FileTypeId -> (detail repo, mapper)  <- add a company here
│   ├── runner.py               #   shared 3-phase flow with resume
│   └── gpa/mapper.py           #   GPA column mapping (company-specific)
├── forecast/                   # JOB 3: empty until built
└── entrypoints/cli.py          # thin CLI; logic stays in the runners
```

## Processing phases (Job 2)

Each file is processed in **three committed phases**, each atomic across the whole
file, so an interrupted run **resumes from the last completed phase** (it skips the
phases already committed and loads the saved voyages):

1. voyages → `LoadStatusId = 3`
2. details → `LoadStatusId = 4`
3. field maps → `LoadStatusId = 5` (fully processed)

Before any write, the mapped rows are **prevalidated** — each voyage needs `VOYAGE`
and `WORK_DATE`. A bad file is rejected whole (before any write) and marked `ERROR`
(99); in a batch run the other files still process. See the LoadStatus lifecycle in
[cli.md](cli.md).

The voyage's descriptive fields — **Vessel, Ocean Carrier, Service, Location, Origin,
Destination** — are written by the `DemandForecast.VoyageFieldMap_upsert` proc, called
once per field: it find-or-creates `FieldValue` and `FieldTypeValue`, then upserts
`VoyageFieldMap`. It's idempotent (reprocessing never duplicates). Equipment type is
encoded on `VoyageDetails.FieldTypeValueEquipTypeId` (ids 1/2/3 = 20CH/40CH/45CH).

## How to add a company (the scaling rule)

- **Ingestion:** add a reader + loader under `ingestion/<company>/` and one line in
  `ingestion/registry.py`.
- **Processing:** add a mapper under `processing/<company>/` (its own column tables) and
  one line in `processing/registry.py`.

The shared files — `session`, `base`, `field_mapping`, both runners, and `writer` —
never change.