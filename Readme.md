# Vessel Demand Forecast

A **database-first** Python data pipeline for vessel demand. It loads company files
into raw tables, turns them into a shared voyage model, and (later) forecasts demand
from that history.

> **The database owns the schema.** This code never creates or alters tables —
> models reflect existing tables only.

## How it works

Three stages, each a separate job. Adding a new company touches only that company's
files — the shared flow doesn't change.

```
  company files
       │
       ▼   (1) ingest
  File_tbl + GpaFileDetail_tbl               — raw rows, per company
       │
       ▼   (2) process
  Voyage_tbl + VoyageDetails_tbl             — shared voyage model
  FieldValue → FieldTypeValue → VoyageFieldMap   — each voyage's attributes
       │
       ▼   (3) forecast   (future)
  demand forecast
```

1. **Ingest** — read a company file, write `File_tbl` + that company's raw detail
   table (`GpaFileDetail_tbl`), in one transaction.
2. **Process** — map the raw rows into the shared `Voyage` / `VoyageDetails` model and
   the field-mapping tables. Runs in resumable phases per file.
3. **Forecast** — future; will read the voyage history via repositories only.

## Quick start

```powershell
cd C:\...\ForecastDemend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py --help
```

Then ingest a file and process what's ready:

```powershell
python run.py ingest --path "C:/files/NineDayVessel.csv" --type GPA   # prints a FileId
python run.py process-pending                                          # process all ready files
```

Every command also takes `--env dev|uat|prod` (default `dev`).

## Documentation

| Topic | Doc |
|-------|-----|
| The 3 jobs, folder structure, processing phases, adding a company | [architecture](documentation/architecture.md) |
| Requirements, `.env` (dev/uat/prod), venv, running the CLI | [setup](documentation/setup.md) |
| CLI commands, `--env`, LoadStatus lifecycle, end-to-end | [cli](documentation/cli.md) |
| Running unit & integration tests | [tests](documentation/tests.md) |
| How the field-mapping tables work | [explanation](documentation/explanation.md) |

A visual diagram of the tables and flow:
[data_pipeline.html](documentation/data_pipeline.html) (open in a browser).

## Branching

- **`main`** is the main branch — it stays stable and releasable at all times.
- Start every new feature on its own branch off `main`, named **`features/<short-name>`**
  (e.g. `features/ncspa-ingestion`), and merge it back into `main` via a pull request.

This is good practice: keeping `main` always-working and isolating each change on its
own `features/` branch means work-in-progress never destabilises the shared branch,
every change is reviewed before it lands, and unfinished or abandoned work is easy to
drop without ever touching `main`.