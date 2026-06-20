from __future__ import annotations

from pathlib import Path
from typing import Any

from factory.utils import to_simple_yaml, write_text


def select_recommended_template(task_type: str, templates_dir: str | Path = "templates") -> str:
    candidates = {
        "multiple_choice": "multiple_choice_harness",
        "classification": "classification_harness",
    }
    preferred = candidates.get(task_type)
    if preferred and (Path(templates_dir) / preferred).exists():
        return preferred
    return "base_harness"


def summarize_input_columns(files: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ["train", "test", "sample_submission"]:
        meta = files.get(key, {})
        summary[key] = {
            "exists": bool(meta.get("exists")),
            "row_count": meta.get("row_count", 0),
            "column_count": meta.get("column_count", len(meta.get("columns", []))),
            "columns": meta.get("columns", []),
            "column_details": meta.get("column_details", []),
        }
    return summary


def build_harness_blueprint(
    spec: dict[str, Any],
    gap_report: dict[str, Any],
    templates_dir: str | Path = "templates",
) -> dict[str, Any]:
    task_type = spec.get("problem", {}).get("task_type", "unknown")
    output = spec.get("output", {})

    return {
        "contest_name": spec.get("contest", {}).get("name", "unknown"),
        "task_type": task_type,
        "task_type_evidence": spec.get("problem", {}).get("task_type_evidence", []),
        "input_files": {
            key: {
                "path": meta.get("path"),
                "exists": bool(meta.get("exists")),
            }
            for key, meta in spec.get("files", {}).items()
        },
        "input_columns_summary": summarize_input_columns(spec.get("files", {})),
        "output_required_columns": output.get("required_columns", []),
        "id_column": output.get("id_column", "unknown"),
        "target_column": output.get("target_column", "unknown"),
        "default_value": output.get("default_value", "1"),
        "recommended_template": select_recommended_template(task_type, templates_dir),
        "loader_requirements": [
            "Load test.csv from contest_source_path.",
            "Preserve id_column values from the test file.",
            "Use UTF-8 CSV handling and keep required output column order.",
        ],
        "solver_requirements": [
            "Use a local baseline solver only.",
            "Return one prediction for every loaded test row.",
            "Use default_value when no better local rule is available.",
        ],
        "verifier_requirements": [
            "Verify submission rows are not empty.",
            "Verify output_required_columns are present in order.",
            "Verify every row has id_column and target_column values.",
        ],
        "submitter_requirements": [
            "Write submission.csv under outputs/.",
            "Use sample_submission.csv column order.",
        ],
        "rule_guard_requirements": [
            "Do not add external LLM API runtime calls.",
            "Do not use external data, internet access, or manual labeling unless rules are confirmed.",
            "Keep leakage_policy strict by default.",
        ],
        "human_decisions_required": gap_report.get("human_required", [])
        + [
            item.get("decision", str(item))
            for item in spec.get("human_decisions", [])
            if item.get("status") == "pending"
        ],
        "known_risks": gap_report.get("risks", []),
    }


def render_harness_blueprint_markdown(blueprint: dict[str, Any]) -> str:
    def bullet_list(items: list[Any]) -> str:
        if not items:
            return "- 없음"
        return "\n".join(f"- {item}" for item in items)

    return "\n".join([
        "# Harness Blueprint",
        "",
        f"- contest_name: {blueprint.get('contest_name')}",
        f"- task_type: {blueprint.get('task_type')}",
        f"- recommended_template: {blueprint.get('recommended_template')}",
        f"- id_column: {blueprint.get('id_column')}",
        f"- target_column: {blueprint.get('target_column')}",
        f"- default_value: {blueprint.get('default_value')}",
        "",
        "## Task Type Evidence",
        "",
        bullet_list(blueprint.get("task_type_evidence", [])),
        "",
        "## Output Required Columns",
        "",
        bullet_list(blueprint.get("output_required_columns", [])),
        "",
        "## Loader Requirements",
        "",
        bullet_list(blueprint.get("loader_requirements", [])),
        "",
        "## Solver Requirements",
        "",
        bullet_list(blueprint.get("solver_requirements", [])),
        "",
        "## Verifier Requirements",
        "",
        bullet_list(blueprint.get("verifier_requirements", [])),
        "",
        "## Submitter Requirements",
        "",
        bullet_list(blueprint.get("submitter_requirements", [])),
        "",
        "## Rule Guard Requirements",
        "",
        bullet_list(blueprint.get("rule_guard_requirements", [])),
        "",
        "## Human Decisions Required",
        "",
        bullet_list(blueprint.get("human_decisions_required", [])),
        "",
        "## Known Risks",
        "",
        bullet_list(blueprint.get("known_risks", [])),
        "",
    ])


def save_harness_blueprint(blueprint: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    out = Path(output_dir)
    yaml_path = write_text(out / "harness_blueprint.yaml", to_simple_yaml(blueprint) + "\n")
    md_path = write_text(out / "harness_blueprint.md", render_harness_blueprint_markdown(blueprint))
    return yaml_path, md_path
