# Tests

Tests live in `tests/` and run with **pytest** (config in `pytest.ini`:
`pythonpath = src`, `testpaths = tests`, `--strict-markers`).

## Layout

- **Unit** — offline, no external dependencies. Marker: `unit`. Located in `tests/unit/`,
  which mirrors `src/app/` (e.g. `tests/unit/processing/` for the mapper/validation tests).
- **Integration** — hit the **live database**, so a working `.env` connection is
  required. Marker: `integration`. Located in `tests/integration/`.

Integration tests run against the **dev** database and tag their rows with a random
GUID; they intentionally leave rows behind (no cleanup), so they can be slow on a
shared DB.

## Run

```powershell
pytest                       # everything
pytest -m unit               # offline only (fast)
pytest -m integration        # live-DB only
pytest -m "not integration"  # everything except live-DB tests
pytest -v                    # verbose
pytest tests/unit/processing/test_gpa_field_mapping.py -v   # a single file
```

Run from the project root (`pytest.ini` sets `pythonpath = src`, so no env setup is
needed). Don't pipe pytest through `Select-Object`/`Tee-Object` — that buffers the
output so a run looks frozen.