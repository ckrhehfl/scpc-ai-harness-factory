from __future__ import annotations

from pathlib import Path
import csv
from typing import Any
from factory.utils import read_text_if_exists


def read_csv_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "columns": [], "row_count": 0}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            columns = next(reader)
        except StopIteration:
            columns = []
            row_count = 0
        else:
            row_count = sum(1 for _ in reader)

    return {
        "path": str(path),
        "exists": True,
        "columns": columns,
        "row_count": row_count,
    }


def read_contest_folder(contest_path: str | Path) -> dict[str, Any]:
    root = Path(contest_path)
    if not root.exists():
        raise FileNotFoundError(f"Contest folder not found: {root}")

    return {
        "root": str(root),
        "description": read_text_if_exists(root / "description.md"),
        "rules": read_text_if_exists(root / "rules.md"),
        "evaluation": read_text_if_exists(root / "evaluation.md"),
        "files": {
            "train": read_csv_meta(root / "train.csv"),
            "test": read_csv_meta(root / "test.csv"),
            "sample_submission": read_csv_meta(root / "sample_submission.csv"),
        },
        "all_files": sorted(p.name for p in root.iterdir() if p.is_file()),
    }
