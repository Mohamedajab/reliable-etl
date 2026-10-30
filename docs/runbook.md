# Operator runbook

## Normal run

Run `reliable-etl <file> --database reporting.db`. A successful response includes the run
ID and read/accepted/rejected counts. Confirm that read equals accepted plus rejected.
Re-running identical file content returns `SKIPPED` and does not create another run.

## Investigating rejects

Group `rejected_record.reason_code` using `sql/operations.sql`, then inspect `raw_record`
for the affected run. Correct the upstream extract and submit a new file. A changed file
has a new SHA-256 fingerprint and is eligible for processing; already accepted transaction
IDs will be quarantined rather than duplicated.

## Failed run

A structural failure (for example, a missing header) rolls back facts and rejects, then
marks the run `FAILED` with the exception text. Fix the file when its structure is invalid. For a transient failure, retry the same file unchanged; every attempt retains its audit record.
Do not edit the reporting tables by hand.

## Recovery guarantee

Facts, rejects and the successful audit update commit in one database transaction. The
run's initial and failed status updates are separate so an operational trace remains even
when the data transaction is rolled back.

