# ReliableETL — replay-safe transaction ingestion

ReliableETL processes daily CSV files without silently losing bad rows or loading the same
transaction twice. The main logic is written in Python and SQL, with no separate orchestration service.

## Guarantees

- identical file content is processed once, even if the file is renamed;
- transaction IDs remain unique across different batches;
- valid facts, rejected rows and final counts commit atomically;
- every attempted file has a durable run record;
- a successful run always reconciles: `read = accepted + rejected`.

## Try it

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
reliable-etl data/inbox/transactions_2025-07-01.csv --database reporting.db
reliable-etl data/inbox/transactions_2025-07-01.csv --database reporting.db
pytest -q
```

The second command reports `SKIPPED`. Query `etl_run`, `transaction_fact` and
`rejected_record` with the statements in [operations.sql](sql/operations.sql).

## What fails a row vs a run

Missing required values, bad dates, invalid quantities/prices and duplicate transaction
IDs reject one row. A structurally unusable file—such as missing required columns—fails
the run. Other valid rows can still be loaded when a row is rejected.

See the [data contract](docs/data-contract.md), [processing flow](docs/flow.md), and
[operator runbook](docs/runbook.md) for validation, replay, and recovery details.

## Retry and recovery

Run `python scripts/operational_demo.py` to try a complete recovery example.
The [HTML report](docs/evidence/operational-demo.html) and
[JSON results](docs/evidence/operational-demo.json) show accepted and rejected rows,
replaying the same file, a broken file and a successful run after correcting it.
Each run uses a new temporary database. The script also checks that a failed
command returns a nonzero exit code.

Failed content can be retried unchanged. Each attempt keeps its own audit record; only
successful file hashes are unique. Existing databases are migrated without dropping facts
or rejected records. A crash can leave a RUNNING audit entry; retrying creates a new attempt.
