"""Transactional, idempotent ingestion for daily retail transaction files."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .schema import SCHEMA

REQUIRED = {"transaction_id", "transaction_date", "customer_id", "product_id", "quantity", "unit_price"}


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    rows_read: int
    rows_accepted: int
    rows_rejected: int
    message: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(row: dict[str, str]) -> tuple[dict[str, object] | None, list[str]]:
    reasons: list[str] = []
    missing = sorted(field for field in REQUIRED if not (row.get(field) or "").strip())
    if missing:
        reasons.append("MISSING_REQUIRED:" + ",".join(missing))
    try:
        parsed_date = date.fromisoformat(row.get("transaction_date") or "")
    except ValueError:
        parsed_date = None
        reasons.append("INVALID_DATE")
    try:
        quantity = int(row.get("quantity") or "")
        if quantity <= 0:
            reasons.append("INVALID_QUANTITY")
    except ValueError:
        quantity = 0
        reasons.append("INVALID_QUANTITY")
    try:
        price = Decimal(row.get("unit_price") or "")
        if not price.is_finite() or price < 0:
            reasons.append("INVALID_PRICE")
    except InvalidOperation:
        price = Decimal(0)
        reasons.append("INVALID_PRICE")
    if reasons:
        return None, sorted(set(reasons))
    try:
        unit_price = price.quantize(Decimal("0.01"))
        amount = (price * quantity).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None, ["INVALID_PRICE"]
    return {
        "transaction_id": row["transaction_id"].strip(),
        "transaction_date": parsed_date.isoformat(),
        "customer_id": row["customer_id"].strip(),
        "product_id": row["product_id"].strip(),
        "quantity": quantity,
        "unit_price": str(unit_price),
        "amount": str(amount),
    }, []


def initialise(connection: sqlite3.Connection) -> None:
    # Existing databases used a global UNIQUE hash, which also blocked failed retries.
    existing = connection.execute("SELECT sql FROM sqlite_master WHERE name='etl_run'").fetchone()
    if existing and "file_sha256 TEXT NOT NULL UNIQUE" in existing[0]:
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            create = existing[0].replace("etl_run", "etl_run_new", 1).replace(
                "file_sha256 TEXT NOT NULL UNIQUE", "file_sha256 TEXT NOT NULL"
            )
            connection.executescript(
                "BEGIN IMMEDIATE;" + create + ";"
                "INSERT INTO etl_run_new SELECT * FROM etl_run;"
                "DROP TABLE etl_run; ALTER TABLE etl_run_new RENAME TO etl_run; COMMIT;"
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS succeeded_file_hash "
        "ON etl_run(file_sha256) WHERE status = 'SUCCEEDED'"
    )


def ingest(path: Path, database: Path) -> RunResult:
    file_hash = fingerprint(path)
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = ON")
    initialise(connection)
    previous = connection.execute(
        "SELECT run_id, rows_read, rows_accepted, rows_rejected FROM etl_run WHERE file_sha256 = ? AND status = 'SUCCEEDED'",
        (file_hash,),
    ).fetchone()
    if previous:
        connection.close()
        return RunResult(previous[0], "SKIPPED", previous[1], previous[2], previous[3], "file content already processed")

    run_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO etl_run(run_id, file_name, file_sha256, started_at, status) VALUES(?,?,?,?, 'RUNNING')",
        (run_id, path.name, file_hash, utc_now()),
    )
    connection.commit()
    read_count = accepted_count = rejected_count = 0
    try:
        connection.execute("BEGIN IMMEDIATE")
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
                raise ValueError(f"file header must include {sorted(REQUIRED)}")
            for row_number, row in enumerate(reader, start=2):
                read_count += 1
                clean, reasons = validate(row)
                if reasons:
                    rejected_count += 1
                    connection.execute(
                        "INSERT INTO rejected_record(run_id,row_number,raw_record,reason_code,rejected_at) VALUES(?,?,?,?,?)",
                        (run_id, row_number, json.dumps(row, sort_keys=True), ";".join(reasons), utc_now()),
                    )
                    continue
                try:
                    connection.execute(
                        """INSERT INTO transaction_fact(
                           transaction_id,transaction_date,customer_id,product_id,quantity,
                           unit_price,amount,source_run_id,loaded_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (*clean.values(), run_id, utc_now()),
                    )
                    accepted_count += 1
                except sqlite3.IntegrityError:
                    rejected_count += 1
                    connection.execute(
                        "INSERT INTO rejected_record(run_id,row_number,raw_record,reason_code,rejected_at) VALUES(?,?,?,?,?)",
                        (run_id, row_number, json.dumps(row, sort_keys=True), "DUPLICATE_TRANSACTION_ID", utc_now()),
                    )
        connection.execute(
            """UPDATE etl_run SET finished_at=?, status='SUCCEEDED', rows_read=?,
               rows_accepted=?, rows_rejected=? WHERE run_id=?""",
            (utc_now(), read_count, accepted_count, rejected_count, run_id),
        )
        connection.commit()
        return RunResult(run_id, "SUCCEEDED", read_count, accepted_count, rejected_count, "load committed")
    except Exception as exc:
        connection.rollback()
        connection.execute(
            "UPDATE etl_run SET finished_at=?, status='FAILED', error_message=? WHERE run_id=?",
            (utc_now(), str(exc), run_id),
        )
        connection.commit()
        raise
    finally:
        connection.close()

