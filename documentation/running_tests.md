# Running the tests

Tests live in `tests/` and run with **pytest** (config in `pytest.ini`:
`pythonpath = src`, `testpaths = tests`).

## Layout

- `tests/unit/` — offline tests, no external dependencies. Marker: `unit`.
- `tests/integration/` — tests that hit the **live database**, so a working
  DB connection (`.env`) is required. Marker: `integration`.

> Note: `tests/integration/test_db_roundtrip.py` is a smoke test that inserts a
> `File` + `GpaFileDetail` row inside a transaction and rolls it back, so the
> live DB is left unchanged.

## Run all tests

```powershell
pytest
```

## Run only one group

```powershell
pytest -m unit          # offline only
pytest -m integration   # live DB only
pytest -m "not integration"   # everything except live-DB tests
```

## Run with verbose output

```powershell
pytest -v
```

## Run a single file

```powershell
pytest tests/integration/test_db_roundtrip.py -v
```