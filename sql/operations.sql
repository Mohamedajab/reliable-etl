-- Most recent executions and their reconciliation status.
SELECT run_id, file_name, started_at, finished_at, status,
       rows_read, rows_accepted, rows_rejected,
       rows_read = rows_accepted + rows_rejected AS is_reconciled
FROM etl_run ORDER BY started_at DESC LIMIT 20;

-- Rejection patterns to prioritise with source-system owners.
SELECT reason_code, COUNT(*) AS rejected_rows
FROM rejected_record GROUP BY reason_code ORDER BY rejected_rows DESC;

-- Daily reporting total after validated loads.
SELECT transaction_date, COUNT(*) AS transactions, ROUND(SUM(amount), 2) AS revenue
FROM transaction_fact GROUP BY transaction_date ORDER BY transaction_date;

