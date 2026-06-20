from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
from typing import Any


def write_run_log(path: str | Path, config: dict[str, Any], row_count: int) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "task_type": config.get("task_type"),
        "solver": config.get("solver", {}).get("name"),
        "row_count": row_count,
        "status": "submission_created",
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
