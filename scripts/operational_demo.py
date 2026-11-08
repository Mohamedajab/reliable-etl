"""Run a recovery example in a temporary database."""
import argparse
import html
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def demonstrate(output: Path):
    events = []
    with tempfile.TemporaryDirectory(prefix="reliable-etl-demo-") as directory:
        root = Path(directory)
        source, database = root / "feed.csv", root / "demo.db"
        header = "transaction_id,transaction_date,customer_id,product_id,quantity,unit_price\n"
        good = header + "T1,2026-11-06,C1,P1,2,12.00\nT2,bad,C2,P1,1,9.00\n"
        for name, contents, expected in (
            ("accepted-and-rejected", good, 0),
            ("identical-replay", good, 0),
            ("malformed-file", "wrong,header\na,b\n", 1),
            ("corrected-recovery", header + "T3,2026-11-06,C3,P1,1,5.00\n", 0),
        ):
            source.write_text(contents, encoding="utf-8")
            started = time.perf_counter()
            result = subprocess.run([sys.executable, "-m", "reliable_etl.cli", str(source), "--database", str(database)], check=False, capture_output=True, text=True, timeout=30)
            assert (result.returncode != 0) == bool(expected), (name, result.stderr)
            with closing(sqlite3.connect(database)) as db:
                db.row_factory = sqlite3.Row
                runs = [dict(row) for row in db.execute("SELECT run_id,status,rows_read,rows_accepted,rows_rejected,error_message FROM etl_run ORDER BY rowid")]
                facts = db.execute("SELECT count(*) FROM transaction_fact").fetchone()[0]
                rejects = db.execute("SELECT count(*) FROM rejected_record").fetchone()[0]
            events.append({"step": name, "timestamp": datetime.now(timezone.utc).isoformat(), "duration_ms": round((time.perf_counter() - started) * 1000, 2), "exit_code": result.returncode,
                           "cli_output": result.stdout.strip(), "failure_type": "ValueError" if "ValueError:" in result.stderr else None, "runs": runs, "facts": facts, "rejected_records": rejects})
        assert [e["facts"] for e in events] == [1, 1, 1, 2]
        assert [e["rejected_records"] for e in events] == [1, 1, 1, 1]
        assert "SKIPPED" in events[1]["cli_output"]
        assert [r["status"] for r in events[-1]["runs"]] == ["SUCCEEDED", "FAILED", "SUCCEEDED"]
    output.mkdir(parents=True, exist_ok=True)
    (output / "operational-demo.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(e[k]))}</td>" for k in ("step", "exit_code", "facts", "rejected_records", "duration_ms")) + "</tr>" for e in events)
    (output / "operational-demo.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>ReliableETL run results</title><style>body{font:16px system-ui;margin:24px}div{overflow:auto}td,th{padding:12px;border:1px solid #aaa}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>ReliableETL recovery demonstration</h1><p>Command results and SQLite run records. The temporary database is removed when the example finishes.</p><div><table><tr><th>Step</th><th>Process exit</th><th>Facts</th><th>Rejected rows</th><th>ms</th></tr>' + rows + '</table></div><h2>Run records</h2><pre>' + html.escape(json.dumps(events, indent=2)) + '</pre></html>', encoding="utf-8")
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/evidence"))
    demonstrate(parser.parse_args().output)
