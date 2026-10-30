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


@pytest.mark.parametrize("price", ["NaN", "Infinity", "1e999"])
def test_non_finite_or_unrepresentable_price_is_rejected(price):
    clean, reasons = validate({
        "transaction_id": "T1", "transaction_date": "2025-01-01", "customer_id": "C1",
        "product_id": "P1", "quantity": "1", "unit_price": price,
    })
    assert clean is None
    assert "INVALID_PRICE" in reasons


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



def test_failed_content_can_be_retried_with_audit_preserved(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("id,value\n1,2\n", encoding="utf-8")
    database = tmp_path / "reporting.db"
    for _ in range(2):
        with pytest.raises(ValueError):
            ingest(source, database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM etl_run WHERE status='FAILED'").fetchone()[0] == 2


def test_legacy_database_migration_preserves_facts(tmp_path):
    from reliable_etl.pipeline import initialise
    from reliable_etl.schema import SCHEMA
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA.replace("file_sha256 TEXT NOT NULL", "file_sha256 TEXT NOT NULL UNIQUE"))
        connection.execute("INSERT INTO etl_run(run_id,file_name,file_sha256,started_at,status) VALUES('r','x','hash','now','SUCCEEDED')")
        connection.execute("INSERT INTO transaction_fact VALUES('T1','2025-01-01','C1','P1',1,2,2,'r','now')")
        connection.commit()
        initialise(connection)
        assert connection.execute("SELECT COUNT(*) FROM transaction_fact").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_transient_failure_retries_same_file(tmp_path, monkeypatch):
    from reliable_etl import pipeline
    source = Path(__file__).parents[1] / "data/inbox/transactions_2025-07-01.csv"
    database = tmp_path / "reporting.db"
    original = pipeline.validate
    def fail(row):
        raise OSError("temporary failure")
    monkeypatch.setattr(pipeline, "validate", fail)
    with pytest.raises(OSError):
        ingest(source, database)
    monkeypatch.setattr(pipeline, "validate", original)
    result = ingest(source, database)
    assert result.status == "SUCCEEDED"
    assert ingest(source, database).status == "SKIPPED"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM etl_run ORDER BY rowid").fetchall() == [("FAILED",), ("SUCCEEDED",)]
