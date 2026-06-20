from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.loader import load_tasks, load_config
from src.solver import BaselineSolver
from src.verifier import verify_submission_rows
from src.submitter import write_submission
from src.logger import write_run_log


def main() -> int:
    config = load_config(ROOT / "configs" / "default.json")
    tasks = load_tasks(config)
    solver = BaselineSolver(default_answer=str(config.get("solver", {}).get("default_answer", "1")))
    rows = solver.solve_all(tasks, config)
    verified = verify_submission_rows(rows, config)

    output_path = ROOT / "outputs" / "submission.csv"
    write_submission(verified, config, output_path)
    write_run_log(ROOT / "outputs" / "harness_run_log.json", config, len(verified))

    print(f"[OK] submission created: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
