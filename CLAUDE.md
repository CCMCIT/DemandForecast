# Project Guide for Claude

## Purpose
Ingest daily files into staging tables, then process them into voyage tables.
Future: forecasting on this data.

- Phase 1a — Ingestion: read a file, write `File_tbl` + `GpaFileDetail_tbl`.
- Phase 1b — Processing: read `GpaFileDetail_tbl`, write `Voyage_tbl` + `VoyageDetails_tbl`.
- File type detected by filename prefix (`GPA`). One format per type.
- Many voyages per file.
- Unpivot: each container-type column (`IM_FULL20`, `IM_FULL40`, ...) becomes one `VoyageDetails` row.

## Database
- Engine: MS SQL Server. Driver: `pyodbc`.
- Schema: `DemandForecast`.
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

## Folder structure (fixed — do not reshape)
```
project/
├── src/
│   ├── config/
│   │   └── settings.py              # folder path, DB conn string, env
│   │
│   ├── db/
│   │   ├── base.py                  # declarative base
│   │   └── session.py               # engine + session factory (unit of work)
│   │
│   ├── models/                      # sqlacodegen once, then manual; reflect existing tables only
│   │   ├── file.py                  # File_tbl
│   │   ├── gpa_file_detail.py       # GpaFileDetail_tbl
│   │   ├── voyage.py                # Voyage_tbl
│   │   ├── voyage_details.py        # VoyageDetails_tbl
│   │   └── lookups.py               # Mode_tbl, Direction_tbl, FieldType*, etc.
│   │
│   ├── repositories/                # "writers" — DB access only
│   │   ├── base_repository.py       # generic CRUD + bulk insert
│   │   ├── file_repository.py
│   │   ├── gpa_file_detail_repository.py
│   │   ├── voyage_repository.py
│   │   └── voyage_details_repository.py
│   │
│   ├── readers/                     # "readers" — file -> rows, no DB
│   │   ├── base_reader.py           # abstract: read(path) -> list[dict]
│   │   ├── gpa_reader.py            # CSV + Excel for GPA
│   │   └── reader_factory.py        # file type -> reader
│   │
│   ├── filetype/
│   │   └── resolver.py              # filename -> file type ("GPA" prefix)
│   │
│   ├── ingestion/                   # file -> File_tbl + <X>FileDetail_tbl
│   │   └── ingestion_service.py
│   │
│   ├── processing/
│   │   ├── base_processor.py        # abstract: detail rows -> voyages
│   │   ├── gpa_processor.py         # group by voyage + unpivot columns
│   │   ├── processor_factory.py     # file type -> processor
│   │   └── mapping/                 # ISOLATED undefined rules
│   │       ├── base_mapper.py       # column -> Mode/Direction/Loaded/Equip
│   │       └── gpa_mapper.py        # stub until rules defined
│   │
│   ├── pipelines/                   # thin orchestration
│   │   ├── ingest_pipeline.py       # scan folder, read, ingest
│   │   └── process_pipeline.py      # pick unprocessed, transform, write
│   │
│   ├── analytics/                   # future forecasting; reads via repositories only
│   │   └── .gitkeep
│   │
│   └── main.py                      # CLI entry point
│
├── tests/
│   ├── readers/
│   ├── repositories/
│   ├── processing/
│   └── pipelines/
│
├── requirements.txt                 # sqlalchemy, pyodbc, pandas, openpyxl, pytest
├── pyproject.toml
└── README.md
```

## Layer responsibilities
- **readers**: parse a file into `list[dict]`. No DB.
- **repositories**: all DB access. The only place that reads/writes tables.
- **filetype/resolver**: map filename to a file type.
- **ingestion**: orchestrate read -> write to `File_tbl` + detail table.
- **processing**: transform detail rows into voyages (group + unpivot).
- **processing/mapping**: the only place that holds Mode/Direction/Loaded/Equip rules.
- **pipelines**: thin orchestration. No business logic.
- **analytics**: reads via repositories only. Never imports readers or processors.

## Coding rules
- Simple over clever. Readable over short.
- One transaction per file: commit all, or rollback and set `LoadStatus = FAILED`.
- Comments only when they add value.
- Follow SOLID principles.
- Reuse code (e.g. `base_repository`, `base_reader`, `base_processor`).
- Factories use explicit dict registration. No auto-discovery.

## Extending later (no core changes)
To add PPA / RPA:
- `models/<x>_file_detail.py` (reflect from live DB)
- `readers/<x>_reader.py` + register in `reader_factory`
- `repositories/<x>_file_detail_repository.py`
- `processing/<x>_processor.py` + `mapping/<x>_mapper.py` + register in `processor_factory`
- add prefix to `filetype/resolver.py`

## Open items (must resolve before the relevant step)
- **Processed marker**: `LoadStatus` only means load succeeded. It does NOT mean a file was processed into voyages. Re-running processing will duplicate. Before building `process_pipeline`, decide the rule: check `Voyage_tbl.FileId` exists, or add a processed flag/date. Ask if unclear.
- **Mapping rules**: column -> Mode/Direction/ContainerLoadedFlag/Equip are undefined. Keep `gpa_mapper.py` a stub until provided.
- **History tables** (`VoyageHistory_tbl`, `VoyageDetailsHistory_tbl`): owner not decided (app / trigger / temporal). Ignore for now. Keep the seam.

## Build order
1. `db/base.py`, `db/session.py`
2. `models` (sqlacodegen from live DB, then clean up)
3. `repositories`
4. `readers` + `filetype/resolver`
5. `ingestion` + `ingest_pipeline`
6. `processing` (with mapper stub) + `process_pipeline`

## Working agreement
- Build only what is asked. Nothing extra.
- If requirements are unclear, ask before coding.
- Keep answers short and clear.
- No code until the step is approved.

## Modularity (microservice-ready, monolith for now)
- Build as a modular monolith. One deployable. Do not split into services yet.
- Each module (ingestion, processing, analytics, services) depends only on:
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