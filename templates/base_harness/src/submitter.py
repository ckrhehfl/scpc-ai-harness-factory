from __future__ import annotations

from pathlib import Path
import csv
from typing import Any


def write_submission(rows: list[dict[str, Any]], config: dict[str, Any], output_path: str | Path) -> Path:
    required_columns = config.get("output", {}).get("required_columns") or []
    if not required_columns:
        raise ValueError("No required_columns in config.output")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=required_columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in required_columns})
    return out
