# Vessel Demand Forecast — Project Overview

A database-first Python pipeline that turns daily vessel files into a shared voyage model, and (later) forecasts demand.

> This page is the 5-minute tour for a new developer: **what the project does**, **how data flows**, and **how to run it**. Deeper docs are linked at the bottom.

## What it does

Shipping companies send daily files listing the vessel voyages expected at a port (a "9-day" report). The pipeline:

1. **Loads** each raw file into the database as-is.
2. **Processes** it into a clean, shared **Voyage** model that every company feeds into.
3. Later, **forecasts** demand from that accumulated history.

> Key rule: **the database owns the schema.** This code never creates or alters tables — the Python models just reflect tables that already exist.

## The pipeline at a glance

| 1 · Ingest | → | 2 · Process | → | 3 · Forecast |
|---|---|---|---|---|
| Read a company file, store the raw rows. | | Map raw rows into the shared voyage model + its attributes. | | Future — predict demand from voyage history. |
| `→ Load_tbl + GpaFileDetail_tbl` | | `→ Voyage_tbl + VoyageDetails_tbl + field maps` | | *(not built yet)* |

Each stage is a separate job. Adding a new company means adding *only that company's* reader/mapper — the shared flow never changes.

## How data flows through the tables

```
  company file (CSV)
        |  ingest
        v
  Load_tbl              one row per file (name, type, load status)
  GpaFileDetail_tbl     one row per raw line in the file
        |  process
        v
  Voyage_tbl            one row per voyage   (unique voyage number)
  VoyageDetails_tbl     container counts per voyage (mode, direction, equipment)
        |  (per descriptive field, via a DB proc)
        v
  FieldValue_tbl   ->   FieldTypeValue_tbl   ->   VoyageFieldMap_tbl
  (raw text)            (typed value)             (links a voyage to it)
```

A voyage's descriptive fields — Vessel, Ocean Carrier, Service, Location, Origin Port, Destination Port — live in the three field-mapping tables. `Voyage_tbl` and `VoyageDetails_tbl` are **temporal** (SQL Server keeps their history automatically).

## Processing runs in resumable phases

Each file is processed in three committed steps. If a run is interrupted, the next run **resumes from the last completed step** instead of redoing everything. A file's `LoadStatusId` records where it is:

| Status | Meaning | Set by |
|:---:|---|---|
| **2** | Inserted into LoadDetail — ready to process | ingest |
| **3** | Voyages written | process — phase 1 |
| **4** | Details written | process — phase 2 |
| **5** | Field maps written — **fully processed** | process — phase 3 |
| **99** | Error — the whole file rolled back | any failure |

Before writing anything, each row is validated (a voyage needs a `VOYAGE` number and a `WORK_DATE`). A bad file is rejected whole and marked **99**; in a batch run the other files still process.

## Field mapping (the four tables)

### What each table is

- **FieldType_tbl** — fixed list of the field types (Vessel, Ocean Carrier…). A lookup.
- **FieldValue_tbl** — distinct raw text values (`"MSC"`, `"AE7"`…).
- **FieldTypeValue_tbl** — a (type + value) pair, e.g. *Ocean Carrier + "MSC"*.
- **VoyageFieldMap_tbl** — links a voyage to a FieldTypeValue.

### How they're filled

For each field, the writer calls the stored proc `VoyageFieldMap_upsert`, which:

1. find-or-creates the **FieldValue**,
2. find-or-creates the **FieldTypeValue**,
3. upserts the **VoyageFieldMap** row.

It's idempotent — reprocessing never creates duplicates.

## How to run it

Everything goes through `run.py` from the project root. Every command also takes `--env dev|uat|prod` (default `dev`).

```bash
# one-time setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# load a file, then process what's ready
python run.py ingest --path "C:/files/NineDayVessel.csv" --type GPA
python run.py process-pending
```

Commands: `ingest` · `ingest-folder` · `process` · `process-next` · `process-pending` · `import-status`

## Where the code lives

```
run.py                     launcher (puts src/ on the path)
src/app/
  lookups.py               enum ids that mirror the DB lookups
  config/settings.py       .env + dev/uat/prod connection strings
  db/
    session.py             engine + session factory
    models/                one class per table (reflected)
    repositories/          all DB queries live here
  ingestion/               JOB 1  (base, registry, runner, gpa/)
  processing/              JOB 2  (dto, field_mapping, validation,
                                   writer, status, runner, gpa/mapper)
  forecast/                JOB 3  (empty)
  entrypoints/cli.py       the CLI
```

To add a company: a reader + loader under `ingestion/<company>/` and a mapper under `processing/<company>/`, each registered with one line. The shared runners/writer don't change.

## Where to go next

- [architecture.md](documentation/architecture.md) — the 3 jobs, folder structure, processing phases in depth
- [setup.md](documentation/setup.md) — requirements, `.env`, running the CLI
- [cli.md](documentation/cli.md) — every command, the LoadStatus lifecycle, end-to-end
- [tests.md](documentation/tests.md) — unit vs integration tests
- [DemandForecast_db_schema.drawio](documentation/DemandForecast_db_schema.drawio) — the full ER diagram