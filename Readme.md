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

The CLI lives at `app.entrypoints.cli`. Source is under `src/`, so put `src` on
`PYTHONPATH` (or use the venv Python directly):

```powershell
$env:PYTHONPATH = "src"
python -m app.entrypoints.cli --help
```

There are two independent commands.

### 1. Ingest a file → `File_tbl` + the company detail table

```powershell
python -m app.entrypoints.cli ingest --path "C:/path/NineDayVessel_091720251700.csv" --type GPA
```

- `--type` is the **FileType**; you pass it explicitly (no detection).
- Inserts one `File_tbl` row and all detail rows in **one transaction**.
- On success prints the new `FileId`. On failure it rolls back and records the
  `File` row with `LoadStatus = False` (FAILED).

### 2. Process a loaded file → `Voyage_tbl` + `VoyageDetails_tbl`

```powershell
python -m app.entrypoints.cli process --file-id 123
```

- Uses the `FileId` printed by `ingest`.
- Reads that file's detail rows, maps each into one `Voyage` plus its
  `VoyageDetails` rows, and commits in one transaction.

> Note: `VoyageDetails.FieldTypeValueEquipTypeId` is a FK to `FieldTypeValue_tbl`.
> The mapping writes ids 1–9, so those rows must exist in `FieldTypeValue_tbl`
> first, or the insert fails on the FK.

### End-to-end

```powershell
$env:PYTHONPATH = "src"
python -m app.entrypoints.cli ingest --path "C:/files/NineDayVessel_091720251700.csv" --type GPA
# -> Ingested ... FileId=123
python -m app.entrypoints.cli process --file-id 123
```

## Architecture

Three separate jobs, never merged. Shared targets are agnostic to the source;
adding a company touches only that company's files.

```
src/app/
├── config/settings.py          # .env -> DB url + paths
├── db/
│   ├── session.py              # engine + SessionLocal (never creates schema)
│   ├── models/                 # reflected models, one per table
│   └── repositories/           # one per table; the ONLY place with DB queries
├── ingestion/                  # JOB 1: file on disk -> raw company table
│   ├── base.py                 #   BaseReader / BaseLoader contracts
│   ├── registry.py             #   FileType -> (reader, loader)   <- add a company here
│   ├── runner.py               #   shared flow, one transaction per file
│   └── gpa/                    #   GPA reader + loader (company-specific)
├── processing/                 # JOB 2: raw table -> Voyage + VoyageDetails
│   ├── dto.py                  #   MappedVoyage/MappedDetail (source-agnostic contract)
│   ├── writer.py               #   VoyageWriter: writes the shared target
│   ├── registry.py             #   FileType -> (detail repo, mapper)  <- add a company here
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