# CLI

Run everything through `run.py` from the project root (see [setup.md](setup.md)).
Every command accepts **`--env dev|uat|prod`** to pick the target database
(default `dev`).

```powershell
python run.py --help
```

## Commands

### `ingest` — a file → `File_tbl` + the company detail table

```powershell
python run.py ingest --path "C:/path/NineDayVessel_091720251700.csv" --type GPA
```

- `--type` is the **FileType** name (no detection): `GPA`, `NCSPA_IMPORTS`, `NCSPA_EXPORTS`.
- Inserts one `File_tbl` row and all detail rows in **one transaction**.
- On success prints the new `FileId` and sets `LoadStatusId = 2` (*Inserted into
  FileDetail*). On failure it rolls back and records the `File` row as `LoadStatusId = 99`
  (*Error*).

### `ingest-folder` — ingest every file in a folder

```powershell
python run.py ingest-folder --type GPA --folder "D:/incoming"
```

- Ingests each file in the folder (defaults to `EXCEL_WATCH_FOLDER`).
- Already-ingested files are skipped. Prints `ingested / skipped / failed` counts.

### `process` — one loaded file → voyages, details, field maps

```powershell
python run.py process --file-id 123
```

- Processes the file in three phases (voyages → details → field maps) and sets
  `LoadStatusId = 5` (*Inserted into FieldMap* = fully processed). Prints each phase.
- **Resumes**: if the file was interrupted earlier it continues from its last
  committed phase instead of redoing finished work.
- On failure: rolls back the current phase, sets `LoadStatusId = 99` (*Error*).

### `process-next` — the next N pending files

```powershell
python run.py process-next --count 3
```

- Processes the next `count` pending files, most-complete first (status **4 → 3 → 2**),
  each in its own run. Prints per-file phases and a summary.

### `process-pending` — every pending file

```powershell
python run.py process-pending
```

- Processes **every** file at status 2 (new), 3 or 4 (resume), each independently —
  one file's failure doesn't stop the rest.
- Files whose `FileType` has no processor yet (e.g. NCSPA) are **skipped**.
- Prints a summary (`processed / skipped / failed`) then per-file lines.

### `import-status` — ingestion summary

```powershell
python run.py import-status
```

- Prints how many files were imported successfully out of the total.

## LoadStatus lifecycle (`LoadStatus_tbl`)

| Id | Meaning | Set by |
|----|---------|--------|
| 1 | Inserted into File | (intermediate) |
| 2 | Inserted into FileDetail | `ingest` success → ready to process |
| 3 | Inserted into Voyage | processing phase 1 |
| 4 | Inserted into VoyageDetail | processing phase 2 |
| 5 | Inserted into FieldMap | processing phase 3 → **fully processed** |
| 99 | Error | any failure |

A file at **5** is refused by `process` (already done). A file left at **3 or 4**
(interrupted) is resumed. A file at **99** is reprocessed from phase 1.

## End-to-end

```powershell
.\.venv\Scripts\Activate.ps1

# ingest (prints FileId, sets LoadStatusId = 2)
python run.py ingest --path "C:/files/NineDayVessel_091720251700.csv" --type GPA

# process that one file...
python run.py process --file-id 123

# ...or process everything that's ready
python run.py process-pending
```