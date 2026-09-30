# Transaction input contract

ReliableETL accepts UTF-8 CSV files with a header row. Column order does not matter, and
additional columns are preserved in rejected-row audit records but are not loaded into the
fact table.

## Required columns

| Column | Accepted value | Loaded representation |
| --- | --- | --- |
| `transaction_id` | Non-empty text | Trimmed text; unique across all successful runs |
| `transaction_date` | ISO date (`YYYY-MM-DD`) | ISO date |
| `customer_id` | Non-empty text | Trimmed text |
| `product_id` | Non-empty text | Trimmed text |
| `quantity` | Integer greater than zero | Integer |
| `unit_price` | Decimal greater than or equal to zero | Decimal rounded to two places |

`amount` is derived as `quantity * unit_price` and rounded to two decimal places. A missing
required header is a structural error and fails the entire run before any facts or rejects are
committed.

## Row rejection codes

Rows that do not satisfy the contract are written to `rejected_record` with their source row
number, complete raw record, and one or more reason codes:

| Code | Meaning |
| --- | --- |
| `MISSING_REQUIRED:<columns>` | One or more required values are empty |
| `INVALID_DATE` | `transaction_date` is not an ISO date |
| `INVALID_QUANTITY` | `quantity` is not an integer greater than zero |
| `INVALID_PRICE` | `unit_price` is not a non-negative decimal |
| `DUPLICATE_TRANSACTION_ID` | The transaction ID already exists in `transaction_fact` |

Multiple validation failures are joined with semicolons. A rejected row does not fail the
batch: the run succeeds when every source row is accounted for as either accepted or rejected.

## Replay behavior

The SHA-256 digest of the complete file is the replay key. Content that already completed
successfully returns `SKIPPED`, even under a different filename. Changed content creates a new
run, while the unique transaction ID constraint still prevents previously accepted business
events from being loaded twice.
