import csv
import sqlite3
from pathlib import Path

import pytest

from reliable_etl.pipeline import ingest, validate


def test_validation_reports_multiple_problems():
    clean, reasons = validate({
        "transaction_id": "T1", "transaction_date": "not-a-date", "customer_id": "",
        "product_id": "P1", "quantity": "0", "unit_price": "-2",
    })
    assert clean is None
    assert "INVALID_DATE" in reasons
    assert "INVALID_QUANTITY" in reasons
    assert "MISSING_REQUIRED:customer_id" in reasons


def test_ingest_is_idempotent_and_audited(tmp_path: Path):
    source = Path(__file__).parents[1] / "data/inbox/transactions_2025-07-01.csv"
    database = tmp_path / "reporting.db"
    first = ingest(source, database)
    second = ingest(source, database)
    assert first.status == "SUCCEEDED"
    assert first.rows_read == first.rows_accepted + first.rows_rejected
    assert second.status == "SKIPPED"
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT COUNT(*) FROM transaction_fact").fetchone()[0] == first.rows_accepted
    assert connection.execute("SELECT COUNT(*) FROM etl_run").fetchone()[0] == 1


def test_duplicate_business_key_is_quarantined(tmp_path: Path):
    database = tmp_path / "reporting.db"
    source = tmp_path / "one.csv"
    fields = ["transaction_id", "transaction_date", "customer_id", "product_id", "quantity", "unit_price"]
    with source.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([
            dict(zip(fields, ["T1", "2025-01-01", "C1", "P1", "1", "2.00"])),
            dict(zip(fields, ["T1", "2025-01-01", "C1", "P1", "1", "2.00"])),
        ])
    result = ingest(source, database)
    assert (result.rows_accepted, result.rows_rejected) == (1, 1)


def test_bad_header_fails_without_partial_facts(tmp_path: Path):
    source = tmp_path / "bad.csv"
    source.write_text("id,value\n1,2\n", encoding="utf-8")
    database = tmp_path / "reporting.db"
    with pytest.raises(ValueError):
        ingest(source, database)
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT COUNT(*) FROM transaction_fact").fetchone()[0] == 0
    assert connection.execute("SELECT status FROM etl_run").fetchone()[0] == "FAILED"

