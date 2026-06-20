from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
from factory.utils import write_json


def generate_harness(
    spec: dict[str, Any],
    template_dir: str | Path = "templates/base_harness",
    output_dir: str | Path = "generated/final_harness",
) -> Path:
    template = Path(template_dir)
    out = Path(output_dir)

    if not template.exists():
        raise FileNotFoundError(f"Template not found: {template}")

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(template, out)

    config = {
        "contest_source_path": spec["contest"]["source_path"],
        "task_type": spec["problem"]["task_type"],
        "input_modalities": spec["problem"].get("input_modalities", []),
        "output": spec["output"],
        "rules": spec["rules"],
        "solver": {
            "name": "baseline_constant_solver",
            "default_answer": spec["output"].get("default_value", "1"),
        },
    }
    write_json(out / "configs" / "default.json", config)
    write_json(out / "contest_spec.json", spec)
    return out
