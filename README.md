# ReliableETL — replay-safe transaction ingestion

ReliableETL processes daily CSV files without silently losing bad rows or loading the same
transaction twice. It is intentionally compact: the reliability properties are visible in
ordinary Python and SQL instead of being hidden behind an orchestration product.

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
the run. This boundary lets a daily feed make progress without accepting ambiguity about
its contract.

See the [processing flow](docs/flow.md) and [operator runbook](docs/runbook.md) for the
replay and recovery model.

