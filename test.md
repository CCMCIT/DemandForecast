# Running Tests

Tests run with **pytest**. Config is in `pytest.ini` (`pythonpath = src`,
`testpaths = tests`).

## Test layout

| Folder | Marker | Needs DB? | What it covers |
|--------|--------|-----------|----------------|
| `tests/unit/` | `unit` | No | Offline tests, no external dependencies |
| `tests/integration/` | `integration` | Yes | Tests that hit the live database (require a working `.env` connection) |

## Run everything

```powershell
pytest
```

## Run only unit tests (offline)

```powershell
pytest -m unit
```

Or by folder:

```powershell
pytest tests/unit
```

## Run only integration tests (live DB)

Requires a reachable database via the `.env` connection string.

```powershell
pytest -m integration
```

Or by folder:

```powershell
pytest tests/integration
```

## Run everything except the live-DB tests

Useful when you have no database connection:

```powershell
pytest -m "not integration"
```

## Useful flags

```powershell
pytest -v                                          # verbose
pytest tests/integration/test_db_roundtrip.py -v   # a single file
```