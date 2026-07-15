# Project Guide for Claude

## Purpose
Ingest daily files into staging tables, then process them into voyage tables.
Future: forecasting on this data.

- Phase 1a — Ingestion: read a file, write `File_tbl` + `GpaFileDetail_tbl`.
- Phase 1b — Processing: read `GpaFileDetail_tbl`, write `Voyage_tbl` + `VoyageDetails_tbl`.
  The voyage's descriptive fields (Vessel / Ocean Carrier / Service / Location / Origin /
  Destination) are written by the DB proc `DemandForecast.VoyageFieldMap_upsert`, called
  once per field — it find-or-creates `FieldValue_tbl` + `FieldTypeValue_tbl` and upserts
  `VoyageFieldMap_tbl`. See `processing/voyage/writer.py::write_fields`.
- File type is chosen per file (CLI `--type`, e.g. `GPA`) and drives the reader/mapper via
  explicit registries. One format per type.
- Many voyages per file.
- Unpivot: each container-type column (`IM_FULL20`, `IM_FULL40`, ...) becomes one `VoyageDetails` row.

## Database
- Engine: MS SQL Server. Driver: `pyodbc`.
- Schema: `DemandForecast`.
- Three environments (dev / uat / prod), each a `DB_CONNECTION_STRING_*` in `.env`. Pick per run
  with the CLI `--env` flag (default `dev`); see `config/settings.py` + `db/session.py`.
- **Database-first. Code NEVER creates or alters tables. No `CREATE TABLE`. No migrations. No Alembic.**
- Models reflect existing tables only.
- For new tables: generate/reflect from the live DB. Do not hand-invent columns.
- If a column name or type is unknown: **ask. Do not guess.**
- Models generated once via `sqlacodegen` from the live DB, then maintained by hand.

## Tech
- Python.
- SQLAlchemy (ORM, manual declarative classes).
- `pyodbc` driver.
- File formats: CSV and Excel. Parsing: `pandas` + `openpyxl`.
- Tests: `pytest`.

## Folder structure
```
project/
├── run.py                           # entry point: `python run.py <command> [--env dev|uat|prod]`
├── requirements.txt                 # sqlalchemy, pyodbc, pandas, openpyxl, python-dotenv, pytest
├── pytest.ini                       # markers (unit / integration); pythonpath = src
├── .env                             # DB_CONNECTION_STRING_{DEV,UAT,PROD}, EXCEL_WATCH_FOLDER
├── project-overview.md              # one-page tour for new developers (renders on GitHub)
├── documentation/                   # schema diagram (.drawio), setup/cli/tests/architecture docs
│
├── src/app/
│   ├── lookups.py                   # IntEnums mirroring DB lookups: FileType, LoadStatus, VoyageStatus, FieldType
│   │
│   ├── config/
│   │   └── settings.py              # .env loading; Env enum; connection_string(env); EXCEL_WATCH_FOLDER
│   │
│   ├── db/
│   │   ├── session.py               # engine + session factory; configure(env) binds dev/uat/prod
│   │   ├── models/                  # DB-first ORM models (reflect existing tables only)
│   │   │   ├── base.py              # declarative base
│   │   │   ├── file.py
│   │   │   ├── gpa_file_detail.py
│   │   │   ├── voyage.py
│   │   │   ├── voyage_details.py
│   │   │   ├── mode.py
│   │   │   ├── direction.py
│   │   │   └── process_log_error.py
│   │   └── repositories/            # ALL DB access — one per table
│   │       ├── file_repository.py
│   │       ├── gpa_file_detail_repository.py
│   │       ├── voyage_repository.py
│   │       ├── voyage_details_repository.py
│   │       ├── mode_repository.py
│   │       ├── direction_repository.py
│   │       └── process_log_error_repository.py
│   │
│   ├── ingestion/                   # file -> File_tbl + <X>FileDetail_tbl
│   │   ├── base.py                  # shared reader/loader contract
│   │   ├── registry.py              # FileTypeId -> (reader, loader)  (explicit dict)
│   │   ├── runner.py                # orchestration: single file + folder
│   │   └── gpa/
│   │       ├── reader.py            # file -> rows (CSV/Excel)
│   │       └── loader.py            # rows -> File_tbl + GpaFileDetail_tbl
│   │
│   ├── processing/                  # one folder per domain (voyage, gate_activity, ...)
│   │   └── voyage/                  # detail rows -> Voyage + VoyageDetails + field maps
│   │       ├── registry.py          # FileTypeId -> (detail repository, mapper)  (explicit dict)
│   │       ├── dto.py               # MappedVoyage / MappedDetail / MappedField (source-agnostic)
│   │       ├── field_mapping.py     # build_fields(row, spec) -> MappedField[]  (shared helper)
│   │       ├── writer.py            # MappedVoyage -> DB  (source-agnostic across GPA/FPA/...)
│   │       ├── runner.py            # two-phase orchestration: voyages, then details + fields
│   │       ├── status.py            # fallen-off classification (Called / Cancelled)
│   │       └── gpa/
│   │           └── mapper.py        # GpaFileDetail row -> MappedVoyage  (the ONLY GPA-aware piece)
│   │
│   ├── forecast/                    # future forecasting; reads via repositories only
│   │
│   └── entrypoints/
│       └── cli.py                   # argparse CLI; commands below, all accept --env
│
└── tests/
    ├── integration/                 # hit the live DB (marker: integration)
    └── unit/                        # offline tests (marker: unit); mirrors src/app/
        └── processing/
            └── voyage/              # voyage mapper / validation tests
```

Top level of `tests/` is the KIND of test (unit / integration). Below it, mirror the
`src/app/` layout (so `processing/voyage/` tests live in `tests/unit/processing/voyage/`).
No other top-level test folders.

CLI commands (`entrypoints/cli.py`): `ingest`, `ingest-folder`, `process`, `process-next`,
`process-pending`, `import-status`. Every command takes `--env dev|uat|prod` (default `dev`).

## Layer responsibilities
- **models**: DB-first ORM definitions. Reflect existing tables; no logic.
- **repositories**: all DB access. The only place that reads/writes tables.
- **ingestion/<x>/reader**: parse a file into rows. No DB.
- **ingestion/<x>/loader**: write rows to `File_tbl` + the detail table.
- **ingestion/runner** (+ `registry`): orchestrate ingestion; registry maps FileType -> reader + loader.
- **processing/<domain>/**: one folder per domain (`voyage`, `gate_activity`, ...). Each owns its
  own mapper/writer/runner; domains do not share a runner (see "Extending later").
- **processing/voyage/<x>/mapper**: turn one raw detail row into a `MappedVoyage`. The only source-aware
  processing piece; holds the explicit column tables (Mode/Direction/Equip and the descriptive fields).
- **processing/voyage/field_mapping**: `build_fields` helper (row + spec -> `MappedField[]`), shared across
  voyage sources (GPA/FPA/...).
- **processing/voyage/writer**: persist a `MappedVoyage` (voyages, details, field maps). Source-agnostic.
- **processing/voyage/runner** (+ `registry`): two-phase orchestration; registry maps FileType -> detail repo + mapper.
- **processing/voyage/status**: classify voyages that fell off the report.
- **entrypoints/cli**: argparse entry; parses args, binds the DB env, delegates to the runners. No logic.
- **forecast**: future; reads via repositories only. Never imports ingestion or processing internals.

## Coding rules
- Simple over clever. Readable over short.
- One transaction per phase: commit all, or roll back and set `LoadStatusId = ERROR` (99).
- Comments only when they add value.
- Follow SOLID principles.
- Reuse code (e.g. `db/models/base.py`, `ingestion/base.py`, `processing/voyage/field_mapping.py`,
  the shared `processing/voyage/writer.py`).
- Registries use explicit dict registration. No auto-discovery.

## Extending later (no core changes)
Two different kinds of extension:

**New external source of an existing domain** (e.g. FPA, another voyage feed) — reuses the
shared voyage writer/runner unchanged:
- add its `FileType` to `lookups.py`
- `db/models/<x>_file_detail.py` (reflect from live DB) + `db/repositories/<x>_file_detail_repository.py`
- `ingestion/<x>/reader.py` + `ingestion/<x>/loader.py` + register in `ingestion/registry.py`
- `processing/voyage/<x>/mapper.py` (its own `<X>_COLUMN_MAP` + `<X>_FIELD_MAP`) + register in `processing/voyage/registry.py`

The field-mapping tables, `voyage/field_mapping.build_fields`, and `voyage/writer` need no changes —
the new mapper just declares which columns feed which `FieldType`.

**New domain** (e.g. gate_activity — data of a different shape, often internal) — its own
self-contained folder `processing/<domain>/` with its own mapper/writer/runner. Domains do not
share a runner; a shared runner is extracted only when a third real domain justifies it (rule of
three), not pre-emptively.

## Resolved design decisions (were open items)
- **Processed marker**: tracked by `LoadStatusId` — 2 = ingested, 3 = voyages, 4 = details,
  5 = field maps (fully processed), 99 = error. `process_file` refuses a file already at 5;
  an interrupted run resumes from its last committed phase (skips 1/2/3 as already done).
- **Mapping rules**: defined in `processing/voyage/gpa/mapper.py` — `GPA_COLUMN_MAP` (Mode/Direction/Equip)
  and `GPA_FIELD_MAP` (the descriptive fields). Explicit tables, no name-sniffing.
- **History tables** (`VoyageHistory_tbl`, `VoyageDetailsHistory_tbl`): SQL Server system-versioned
  (temporal). The DB maintains them; the app relies on the seam, no ORM models.

## Still open
- **ExternalId resolution**: `FieldTypeValue.ExternalId` / `ExternalNotifFlag` — resolving a value to
  an id in an external master table via `FieldType.ExternalWhereClause` (types 3 & 5 only) — is not
  built. Left NULL for now. Design separately before implementing.

## Build order (as built)
1. `db/models/base.py`, `db/session.py`
2. `db/models` (reflect from live DB, then clean up)
3. `db/repositories`
4. `ingestion` (`base`, `gpa/reader`, `gpa/loader`, `registry`) + `ingestion/runner`
5. `processing/voyage` (`dto`, `field_mapping`, `gpa/mapper`, `writer`, `status`, `registry`) + `processing/voyage/runner`
6. `entrypoints/cli.py` (+ `run.py`)

## Working agreement
- Build only what is asked. Nothing extra.
- If requirements are unclear, ask before coding.
- Keep answers short and clear.
- No code until the step is approved.

## Modularity (microservice-ready, monolith for now)
- Build as a modular monolith. One deployable. Do not split into services yet.
- Each module (ingestion, processing, forecast) depends only on:
  models, repositories, and its own code. No module imports another module's internals.
- Cross-module calls go through a service or repository interface, never direct internal functions.
- No shared mutable state between modules. Pass data explicitly.
- A module must be movable into its own deployable by changing only its entry point,
  not its logic.
- Keep transaction boundaries inside one module. Do not span a transaction across modules.

## Before splitting into services (ask first)
- Define which service owns which tables. One writer per table.
- Replace in-process calls with an explicit contract (REST or queue).
- Replace the per-file transaction with an outbox or saga if a flow crosses services.
- Do not split without a concrete driver (scaling, team, release cadence).