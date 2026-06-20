from __future__ import annotations

from typing import Any


def verify_submission_rows(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    output = config.get("output", {})
    required_columns = output.get("required_columns") or []
    if not required_columns:
        raise ValueError("No required_columns in config.output")

    for idx, row in enumerate(rows):
        missing = [col for col in required_columns if col not in row]
        if missing:
            raise ValueError(f"Row {idx} missing required columns: {missing}")
        for col in required_columns:
            if row.get(col) is None or str(row.get(col)) == "":
                raise ValueError(f"Row {idx} has empty value for column: {col}")
    return rows
