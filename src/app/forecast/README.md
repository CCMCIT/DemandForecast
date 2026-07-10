# Forecasting

Hybrid data-access for the chassis demand-forecasting model store. Split by
**layer**, not by feature. Writes with a constraint attached go through T-SQL
procedures; reads and statistics stay in Python.

## The one rule
**If it writes and has a constraint attached, it's a proc. Otherwise it's Python.**
This keeps the T-SQL surface small, stable, and rarely touched.

## Layers
| Path | Layer | Contains | Tested by |
|------|-------|----------|-----------|
| `sql` | write surface | TVP types + procs (score run, actuals upsert, register model) | integration |
| `db` | access | one engine + `WriteGateway` / `ReadGateway` | integration |
| `forecast` | domain | pure scoring math + `TrainedModel` value object (no I/O) | unit |
| `pipelines` | orchestration | compute-then-commit glue scripts | smoke run |

## Data flow (a scoring run)
1. Hold a `TrainedModel` (from training - carries coefficients + (X'X)^-1).
2. `run_scoring` computes point + prediction interval for every horizon day,
   entirely in memory.
3. One `WriteGateway.score_run(...)` -> one atomic proc call (batch + inputs +
   predictions). No transaction is straddled.

## Why the procs
They centralize what Python must not be trusted to remember per call: temporal
period columns are never named, `modified_by` is threaded through, FK insert
order is fixed, and actuals is a MERGE upsert. Numerics cross as Decimal at the
column scale so DECIMAL(18,8) never degrades to float on write.

## Reconciliation (pending, pre-production)
`db/engine.py` mirrors the data team's `app/db/session.py` and is meant to
collapse into it. Open decisions before deploy: shared engine/session, the
proc-only vs ORM-ok table boundary, and the actuals handoff (their sourcing
pipeline should stop at source tables and hand off to `usp_upsert_actuals`).

Requires: `sqlalchemy`, `pyodbc`, `pandas`, `numpy`, `scipy`.
