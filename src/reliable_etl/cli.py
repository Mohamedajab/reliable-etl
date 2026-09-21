from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import ingest


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a daily transaction CSV exactly once")
    parser.add_argument("file", type=Path)
    parser.add_argument("--database", type=Path, default=Path("reporting.db"))
    args = parser.parse_args()
    result = ingest(args.file, args.database)
    print(
        f"{result.status}: run={result.run_id} read={result.rows_read} "
        f"accepted={result.rows_accepted} rejected={result.rows_rejected} ({result.message})"
    )


if __name__ == "__main__":
    main()

