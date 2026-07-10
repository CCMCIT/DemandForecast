# Vessel Demand Forecast

A database-first Python data pipeline. It ingests company files into raw tables,
processes them into the shared `Voyage` / `VoyageDetails` model plus the
field-mapping tables, and (later) forecasts demand.

**The DB owns the schema** — this code never creates or alters tables; models
reflect existing tables only.

## Quick start

```powershell
cd C:\...\ForecastDemend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py --help
```

## Documentation

| Topic | Doc |
|-------|-----|
| The 3 jobs, folder structure, processing phases, adding a company | [documentation/architecture.md](documentation/architecture.md) |
| Requirements, `.env` (dev/uat/prod), venv, running the CLI | [documentation/setup.md](documentation/setup.md) |
| CLI commands, the `--env` flag, LoadStatus lifecycle, end-to-end | [documentation/cli.md](documentation/cli.md) |
| Running unit & integration tests, CI | [documentation/tests.md](documentation/tests.md) |

A visual diagram of the tables and processing flow is in
[documentation/data_pipeline.html](documentation/data_pipeline.html) (open in a browser).