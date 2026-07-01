# Vessel Demand Forecast

A database-first Python data pipeline. It ingests company files into raw tables,
processes them into the shared `Voyage` / `VoyageDetails` model, and (later)
forecasts demand. The **DB owns the schema** — this code never creates or alters
tables; models reflect existing tables only.

## Requirements

- Python 3.11
- ODBC Driver 17 for SQL Server
- A reachable MS SQL Server database
- A `.env` file at the project root:

  ```
  DB_CONNECTION_STRING=mssql+pyodbc://USER:PASSWORD@HOST/DATABASE?driver=ODBC+Driver+17+for+SQL+Server
  EXCEL_WATCH_FOLDER=C:/path/to/incoming/files
  ```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Running the CLI

**Where to run from:** always the **project root** — the folder that contains
`run.py` (`...\ForecastDemend`). Run everything through `run.py`; it puts `src/`
on the path for you, so there is no `PYTHONPATH` to set and you never `cd` into
`src/`.

**Steps (PowerShell):**

```powershell
# 1. go to the project root
cd C:\Users\nbutnejski\Desktop\CCM_Workplace\work\PythonFlask\ForecastDemend

# 2. activate the virtualenv (once per terminal; prompt then shows (.venv))
.\.venv\Scripts\Activate.ps1

# 3. run a command
python run.py --help
```

If activating the venv is blocked by an execution policy, either allow it for the
session with `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`,
or skip activation and call the venv Python directly:
`.\.venv\Scripts\python.exe run.py --help`.

There are three commands.

### 1. Ingest a file → `File_tbl` + the company detail table

```powershell
python run.py ingest --path "C:/path/NineDayVessel_091720251700.csv" --type GPA
```

- `--type` is the **FileType** name; you pass it explicitly (no detection).
  Accepted values: `GPA`, `NCSPA_IMPORTS`, `NCSPA_EXPORTS` (mapped to `FileTypeId`).
- Inserts one `File_tbl` row and all detail rows in **one transaction**.
- On success prints the new `FileId` and sets `LoadStatusId = 2`
  (*Inserted into FileDetail*). On failure it rolls back and records the `File`
  row with `LoadStatusId = 5` (*Error*).

### 2. Process one loaded file → `Voyage_tbl` + `VoyageDetails_tbl`

```powershell
python run.py process --file-id 123
```

- Uses the `FileId` printed by `ingest`.
- Reads that file's detail rows, maps each into one `Voyage` plus its
  `VoyageDetails` rows, commits in one transaction, and sets
  `LoadStatusId = 4` (*Inserted into VoyageDetail*). On failure: roll back and
  set `LoadStatusId = 5` (*Error*).

### 3. Process all pending files → `Voyage_tbl` + `VoyageDetails_tbl`

```powershell
python run.py process-pending
```

- Finds **every** file with `LoadStatusId = 2` (*Inserted into FileDetail*) and
  processes each in its **own** transaction (one file's failure doesn't stop the
  rest).
- Files whose `FileType` has no processor yet (e.g. NCSPA) are **skipped**,
  leaving their status unchanged.
- Prints a summary: `processed` / `skipped` / `failed` counts, then per-file lines.

> Note: `VoyageDetails.FieldTypeValueEquipTypeId` is a FK to `FieldTypeValue_tbl`.
> The GPA mapping writes ids 1, 2, 3 (container sizes 20/40/45; MT → NULL), so
> those rows must exist in `FieldTypeValue_tbl` first, or the insert fails on the
> FK (the file is then marked `LoadStatusId = 5`).

### LoadStatus lifecycle (`LoadStatus_tbl`)

| Id | Meaning | Set by |
|----|---------|--------|
| 1 | Inserted into File | (intermediate) |
| 2 | Inserted into FileDetail | `ingest` success → ready to process |
| 3 | Inserted into Voyage | (intermediate) |
| 4 | Inserted into VoyageDetail | `process` / `process-pending` success |
| 5 | Error | any failure |

### End-to-end

```powershell
.\.venv\Scripts\Activate.ps1
python run.py ingest --path "C:/files/NineDayVessel_091720251700.csv" --type GPA
# -> Ingested ... FileId=123   (LoadStatusId=2)
python run.py process --file-id 123      # one file
# or, process everything that's ready:
python run.py process-pending
```

## Architecture

Three separate jobs, never merged. Shared targets are agnostic to the source;
adding a company touches only that company's files.

```
run.py                          # launcher: `python run.py <command>` (puts src/ on the path)
src/app/
├── lookups.py                  # FileType / LoadStatus ids mirroring the DB lookups
├── config/settings.py          # .env -> DB url + paths
├── db/
│   ├── session.py              # engine + SessionLocal (never creates schema)
│   ├── models/                 # reflected models, one per table
│   └── repositories/           # one per table; the ONLY place with DB queries
├── ingestion/                  # JOB 1: file on disk -> raw company table
│   ├── base.py                 #   BaseReader / BaseLoader contracts
│   ├── registry.py             #   FileTypeId -> (reader, loader)   <- add a company here
│   ├── runner.py               #   shared flow, one transaction per file
│   └── gpa/                    #   GPA reader + loader (company-specific)
├── processing/                 # JOB 2: raw table -> Voyage + VoyageDetails
│   ├── dto.py                  #   MappedVoyage/MappedDetail (source-agnostic contract)
│   ├── writer.py               #   VoyageWriter: writes the shared target
│   ├── registry.py             #   FileTypeId -> (detail repo, mapper)  <- add a company here
│   ├── runner.py               #   shared flow, picks mapper by FileType
│   └── gpa/mapper.py           #   GPA column mapping (company-specific)
├── forecast/                   # JOB 3: empty until built
└── entrypoints/cli.py          # thin CLI; logic stays in the runners
```

### How to add a company (the scaling rule)

- **Ingestion:** add a reader + loader under `ingestion/<company>/` and one line
  in `ingestion/registry.py`.
- **Processing:** add a mapper under `processing/<company>/` and one line in
  `processing/registry.py`.

The shared files — `session`, `base`, both `runner`s, and `writer` — never change.

## Tests

See `test.md`. Unit tests (`tests/unit/`, offline) and integration tests
(`tests/integration/`, live DB) are separated by folder and pytest marker.