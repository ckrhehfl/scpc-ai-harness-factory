from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime
import json
import shutil


def next_run_dir(runs_root: str | Path = "runs") -> Path:
    root = Path(runs_root)
    root.mkdir(parents=True, exist_ok=True)
    existing = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("run_")]
    next_id = len(existing) + 1
    return root / f"run_{next_id:03d}"


def save_run_log(
    spec: dict[str, Any],
    gap_report_path: str | Path,
    harness_dir: str | Path,
    runs_root: str | Path = "runs",
) -> Path:
    run_dir = next_run_dir(runs_root)
    run_dir.mkdir(parents=True, exist_ok=True)

    log = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "contest_source_path": spec["contest"]["source_path"],
        "task_type": spec["problem"]["task_type"],
        "harness_dir": str(harness_dir),
        "gap_report_path": str(gap_report_path),
        "status": "factory_generated",
    }
    (run_dir / "run_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

    spec_json = Path("generated/contest_spec.json")
    if spec_json.exists():
        shutil.copy2(spec_json, run_dir / "contest_spec.json")
    gap = Path(gap_report_path)
    if gap.exists():
        shutil.copy2(gap, run_dir / "gap_report.md")
    return run_dir
