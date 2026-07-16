# Setup

## Requirements

- Python 3.11
- ODBC Driver 17 for SQL Server
- A reachable MS SQL Server database

## Environment (`.env`)

Create a `.env` file at the project root. There are **three database environments**;
you pick one per run with the CLI `--env` flag (default `dev`):

```
DB_CONNECTION_STRING_DEV=mssql+pyodbc://USER:PASSWORD@HOST/DATABASE?driver=ODBC+Driver+17+for+SQL+Server
DB_CONNECTION_STRING_UAT=mssql+pyodbc://USER:PASSWORD@HOST/DATABASE?driver=ODBC+Driver+17+for+SQL+Server
DB_CONNECTION_STRING_PROD=mssql+pyodbc://USER:PASSWORD@HOST/DATABASE?driver=ODBC+Driver+17+for+SQL+Server

EXCEL_WATCH_FOLDER=C:/path/to/incoming/files
```

Only the environment you actually select needs to be filled in. Keep `.env` out of
version control — it holds credentials.

## Install

Dependencies are listed in **`requirements.txt`** (SQLAlchemy, pyodbc, python-dotenv,
pytest). Install them into a virtualenv:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If activating the venv is blocked by an execution policy, either allow it for the
session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

or skip activation and call the venv Python directly:
`.\.venv\Scripts\python.exe run.py --help`.

## Running the CLI

**Recommended — `python run.py <command>` from the project root.** `run.py` puts
`src/` on the path for you, so there is no `PYTHONPATH` to set and you never `cd`
into `src/`.

```powershell
cd C:\...\DemandForecast
.\.venv\Scripts\Activate.ps1
python run.py --help
```

### Where you run from matters

The `app` package lives in `src/`, and the project is **not** pip-installed, so
Python only finds `app` if `src/` is on the path. Two valid ways to run — pick one:

| Command | Run it from | Notes |
|---------|-------------|-------|
| `python run.py <command>` | **project root** (`...\DemandForecast`) | Recommended. `run.py` adds `src/` to the path for you. |
| `python -m app.entrypoints.cli <command>` | **the `src/` folder** | Direct module form. `python -m` only puts the *current* folder on the path, so you must `cd src` first. |

Running `python -m app.entrypoints.cli` from the project root fails with
`ModuleNotFoundError: No module named 'app'` — from the root, `app` isn't on the path.
Either `cd src` first, or just use `python run.py` from the root.

For the commands themselves, see [cli.md](cli.md).