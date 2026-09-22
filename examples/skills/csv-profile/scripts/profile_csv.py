"""Read-only CSV profile. Standard library only; stores distinct rows in memory."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

def profile(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        headers = next(reader, [])
        missing = [0] * len(headers)
        seen = set()
        rows = duplicates = malformed = 0
        for row in reader:
            rows += 1
            malformed += len(row) != len(headers)
            key = tuple(row)
            duplicates += key in seen
            seen.add(key)
            for i in range(len(headers)):
                missing[i] += i >= len(row) or not row[i].strip()
    return {"columns": headers, "rows": rows, "missing_by_column_index": missing,
            "duplicate_rows": duplicates, "malformed_rows": malformed}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(profile(args.path), ensure_ascii=False, indent=2))
    except (OSError, UnicodeError, csv.Error) as exc:
        parser.exit(2, f"Cannot profile this file: {type(exc).__name__}\n")
