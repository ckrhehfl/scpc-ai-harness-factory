from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
from factory.utils import write_json


def generate_harness(
    spec: dict[str, Any],
    blueprint: dict[str, Any] | None = None,
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
        "verifier": {
            "test_csv_path": str(Path(spec["contest"]["source_path"]) / "test.csv"),
            "sample_submission_csv_path": str(Path(spec["contest"]["source_path"]) / "sample_submission.csv"),
            "required_columns": spec["output"].get("required_columns", []),
            "id_column": spec["output"].get("id_column"),
            "target_column": spec["output"].get("target_column"),
            "value_constraints": spec["output"].get("value_constraints"),
        },
        "rules": spec["rules"],
        "solver": {
            "name": "baseline_constant_solver",
            "default_answer": (blueprint or {}).get("default_value", spec["output"].get("default_value", "1")),
        },
    }
    if blueprint is not None:
        config["harness_blueprint"] = {
            "recommended_template": blueprint.get("recommended_template", "base_harness"),
            "verifier_requirements": blueprint.get("verifier_requirements", []),
            "human_decisions_required": blueprint.get("human_decisions_required", []),
            "known_risks": blueprint.get("known_risks", []),
        }
    write_json(out / "configs" / "default.json", config)
    write_json(out / "contest_spec.json", spec)
    return out
