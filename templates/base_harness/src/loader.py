from __future__ import annotations

from pathlib import Path
import csv
import json
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def load_tasks(config: dict[str, Any]) -> list[dict[str, Any]]:
    contest_path = Path(config["contest_source_path"])
    test_path = contest_path / "test.csv"
    if not test_path.exists():
        raise FileNotFoundError(f"test.csv not found: {test_path}")

    with test_path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
