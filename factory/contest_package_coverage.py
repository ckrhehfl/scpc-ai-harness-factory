from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from factory.contest_package_manifest import (
    ContestPackageManifestError,
    build_manifest_source_map,
    load_contest_package_manifest,
)
from factory.utils import to_simple_yaml, write_json, write_text


SCHEMA_VERSION = "v0.9B"
ARTIFACT_TYPE = "contest_package_coverage"
STATUSES = {
    "captured",
    "modeled_confirmed",
    "modeled_unknown",
    "not_modeled",
    "missing_source",
    "conflicting",
}
CORE_FIELD_PATHS = [
    "problem.task_type",
    "problem.evaluation_metric",
    "rules.allowed_language",
    "rules.external_api_allowed",
    "rules.external_data_allowed",
    "rules.pretrained_model_allowed",
    "rules.internet_allowed",
    "rules.manual_labeling_allowed",
    "rules.leakage_policy",
    "output.required_file",
    "output.required_columns",
    "output.value_constraints",
]
NOT_MODELED_TOPICS = [
    "participation mode",
    "round schedule",
    "code-share policy",
    "submission UI max file count",
    "submission encoding",
    "finalist code deliverable",
    "finalist presentation deliverable",
    "legal/IP terms",
]
HIGH_RISK_PATHS = [
    "problem.evaluation_metric",
    "rules.external_api_allowed",
    "rules.external_data_allowed",
    "rules.pretrained_model_allowed",
    "rules.internet_allowed",
    "finalist.code_submission_format",
    "finalist.presentation_submission_format",
]


class ContestPackageCoverageError(ValueError):
    pass


def load_json_artifact(path: str | Path, label: str) -> dict[str, Any]:
    artifact_path = Path(path)
    if not artifact_path.exists():
        raise ContestPackageCoverageError(f"Missing required artifact {label}: {artifact_path}")
    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContestPackageCoverageError(f"Malformed JSON in {label}: {exc}") from exc
    except OSError as exc:
        raise ContestPackageCoverageError(f"Could not read {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContestPackageCoverageError(f"{label} must be a JSON object")
    return data


def build_contest_package_coverage(
    contest_path: str | Path,
    *,
    artifacts_dir: str | Path,
) -> dict[str, Any]:
    contest_root = Path(contest_path)
    if not contest_root.exists():
        raise ContestPackageCoverageError(f"Contest folder not found: {contest_root}")
    artifacts = Path(artifacts_dir)
    try:
        manifest = load_contest_package_manifest(contest_root)
    except ContestPackageManifestError as exc:
        raise ContestPackageCoverageError(str(exc)) from exc

    scan_report = load_json_artifact(artifacts / "input_scan_report.json", "input_scan_report.json")
    evidence_index = load_json_artifact(artifacts / "evidence_index.json", "evidence_index.json")
    contest_spec = load_json_artifact(artifacts / "contest_spec.json", "contest_spec.json")

    source_map = build_manifest_source_map(manifest)
    scan_files = _scan_files_by_path(scan_report)
    evidence_by_file = _evidence_by_file(evidence_index)
    applied_overrides = _applied_overrides_by_path(contest_spec)
    warnings: list[dict[str, Any]] = []

    source_coverage = [
        _source_coverage_item(
            source_path=source_path,
            declared=declared,
            contest_root=contest_root,
            scan_files=scan_files,
            evidence_by_file=evidence_by_file,
        )
        for source_path, declared in sorted(source_map.items())
    ]
    for item in source_coverage:
        if item["status"] == "missing_source":
            warnings.append({
                "status": "missing_source",
                "path": item["path"],
                "message": "Manifest source is missing from disk or scan artifacts.",
            })

    core_field_coverage = [
        _field_coverage_item(path, contest_spec, applied_overrides)
        for path in CORE_FIELD_PATHS
    ]
    declared_unknown_coverage = _declared_unknown_coverage(
        manifest,
        contest_spec,
        applied_overrides,
        warnings,
    )
    high_risk_unknowns = _high_risk_unknowns(contest_spec, applied_overrides)
    not_modeled_topics = [
        {
            "topic": topic,
            "status": "not_modeled",
            "source_captured": bool(source_coverage) or bool(scan_files),
        }
        for topic in NOT_MODELED_TOPICS
    ]

    coverage = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "contest_path": str(contest_root),
        "manifest_present": manifest is not None,
        "source_summary": {
            "manifest_source_count": len(source_map),
            "scan_file_count": len(scan_files),
            "evidence_record_count": len(evidence_index.get("records", [])),
            "document_chunk_evidence_count": sum(
                1 for record in evidence_index.get("records", []) if ":document_chunk:" in record.get("key", "")
            ),
        },
        "source_coverage": source_coverage,
        "core_field_coverage": core_field_coverage,
        "declared_unknown_coverage": declared_unknown_coverage,
        "not_modeled_topics": not_modeled_topics,
        "high_risk_unknowns": high_risk_unknowns,
        "warnings": warnings,
    }
    _validate_coverage(coverage)
    return coverage


def render_contest_package_coverage_markdown(coverage: dict[str, Any]) -> str:
    _validate_coverage(coverage)
    lines = [
        "# Contest Package Coverage",
        "",
        f"- schema_version: {coverage['schema_version']}",
        f"- contest_path: {coverage['contest_path']}",
        f"- manifest_present: {coverage['manifest_present']}",
        "",
        "## Source Summary",
        "",
    ]
    for key, value in coverage["source_summary"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Source Coverage", ""])
    for item in coverage["source_coverage"]:
        lines.append(
            f"- `{item['path']}` / status={item['status']} / role={item.get('role')} / "
            f"kind={item.get('source_kind')} / chunks={len(item.get('document_chunk_evidence_ids', []))}"
        )

    lines.extend(["", "## Core Field Coverage", ""])
    for item in coverage["core_field_coverage"]:
        override = " / override" if item.get("override") else ""
        lines.append(f"- {item['path']}: {item['status']}{override}")

    lines.extend(["", "## Declared Unknown Coverage", ""])
    for item in coverage["declared_unknown_coverage"]:
        lines.append(f"- {item['path']}: {item['status']}")

    lines.extend(["", "## High-risk Unknowns", ""])
    for item in coverage["high_risk_unknowns"]:
        lines.append(f"- {item['path']}: {item['status']} / impact={item['impact']}")

    lines.extend(["", "## Not-modeled Topics", ""])
    for item in coverage["not_modeled_topics"]:
        lines.append(f"- {item['topic']}: {item['status']} / source_captured={item['source_captured']}")

    if coverage["warnings"]:
        lines.extend(["", "## Warnings", "", "```yaml", to_simple_yaml(coverage["warnings"]), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def save_contest_package_coverage(coverage: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    _validate_coverage(coverage)
    markdown = render_contest_package_coverage_markdown(coverage)
    out = Path(output_dir)
    return {
        "json": write_json(out / "contest_package_coverage.json", coverage),
        "md": write_text(out / "contest_package_coverage.md", markdown),
    }


def _scan_files_by_path(scan_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = scan_report.get("files")
    if not isinstance(files, list):
        raise ContestPackageCoverageError("input_scan_report.json field 'files' must be a list")
    by_path: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ContestPackageCoverageError("Each input scan file item must be an object with path")
        by_path[item["path"]] = item
    return by_path


def _evidence_by_file(evidence_index: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    records = evidence_index.get("records")
    if not isinstance(records, list):
        raise ContestPackageCoverageError("evidence_index.json field 'records' must be a list")
    by_file: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("source_file"), str):
            raise ContestPackageCoverageError("Each evidence record must be an object with source_file")
        by_file.setdefault(record["source_file"], []).append(record)
    return by_file


def _source_coverage_item(
    *,
    source_path: str,
    declared: dict[str, Any],
    contest_root: Path,
    scan_files: dict[str, dict[str, Any]],
    evidence_by_file: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    file_exists = (contest_root / source_path).is_file()
    scan_item = scan_files.get(source_path)
    records = evidence_by_file.get(source_path, [])
    inventory_ids = [
        record["evidence_id"]
        for record in records
        if isinstance(record.get("key"), str) and record["key"].endswith(":inventory")
    ]
    chunk_ids = [
        record["evidence_id"]
        for record in records
        if isinstance(record.get("key"), str) and ":document_chunk:" in record["key"]
    ]
    status = "captured" if file_exists and scan_item and inventory_ids else "missing_source"
    item = {
        "path": source_path,
        "status": status,
        "file_exists": file_exists,
        "input_scan_included": scan_item is not None,
        "inventory_evidence_ids": inventory_ids,
        "document_chunk_evidence_ids": chunk_ids,
        "role": declared.get("role"),
        "visibility": declared.get("visibility"),
        "source_kind": declared.get("source_kind"),
    }
    if "origin" in declared:
        item["origin"] = declared["origin"]
    return item


def _field_coverage_item(
    path: str,
    spec: dict[str, Any],
    applied_overrides: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    exists, value = _get_path(spec, path)
    if not exists:
        status = "not_modeled"
    elif _is_unknown(value):
        status = "modeled_unknown"
    else:
        status = "modeled_confirmed"
    item = {"path": path, "status": status, "value": value if exists else None}
    if path in applied_overrides:
        item["override"] = applied_overrides[path]
    return item


def _declared_unknown_coverage(
    manifest: dict[str, Any] | None,
    spec: dict[str, Any],
    applied_overrides: dict[str, dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    declared = manifest.get("declared_unknowns", []) if manifest else []
    coverage: list[dict[str, Any]] = []
    for path in declared:
        exists, value = _get_path(spec, path)
        if not exists:
            status = "not_modeled"
        elif _is_unknown(value):
            status = "modeled_unknown"
        elif path in applied_overrides:
            status = "modeled_confirmed"
        else:
            status = "conflicting"
            warnings.append({
                "status": "conflicting",
                "path": path,
                "message": "Declared official unknown has a non-unknown ContestSpec value without a human override.",
            })
        item = {
            "path": path,
            "status": status,
            "spec_path_exists": exists,
            "current_value": value if exists else None,
            "unknown_preserved": exists and _is_unknown(value),
        }
        if path in applied_overrides:
            item["override"] = applied_overrides[path]
        coverage.append(item)
    return coverage


def _high_risk_unknowns(
    spec: dict[str, Any],
    applied_overrides: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in HIGH_RISK_PATHS:
        exists, value = _get_path(spec, path)
        if not exists:
            status = "not_modeled"
        elif _is_unknown(value):
            status = "modeled_unknown"
        else:
            continue
        item = {
            "path": path,
            "status": status,
            "impact": "high",
            "current_value": value if exists else None,
        }
        if path in applied_overrides:
            item["override"] = applied_overrides[path]
        items.append(item)
    return items


def _applied_overrides_by_path(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    applied = spec.get("decision_overrides", {}).get("applied", [])
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(applied, list):
        return result
    for item in applied:
        if isinstance(item, dict) and isinstance(item.get("item"), str):
            result[item["item"]] = {
                "source": item.get("source"),
                "status": item.get("status"),
                "value": item.get("value"),
            }
    return result


def _get_path(data: dict[str, Any], dotted_path: str) -> tuple[bool, Any]:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _is_unknown(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value == "" or value.lower() == "unknown"
    return False


def _validate_coverage(coverage: dict[str, Any]) -> None:
    if coverage.get("schema_version") != SCHEMA_VERSION:
        raise ContestPackageCoverageError("Invalid coverage schema_version")
    if coverage.get("artifact_type") != ARTIFACT_TYPE:
        raise ContestPackageCoverageError("Invalid coverage artifact_type")
    for section in [
        "source_coverage",
        "core_field_coverage",
        "declared_unknown_coverage",
        "not_modeled_topics",
        "high_risk_unknowns",
        "warnings",
    ]:
        if not isinstance(coverage.get(section), list):
            raise ContestPackageCoverageError(f"Coverage field '{section}' must be a list")
    for section in ["source_coverage", "core_field_coverage", "declared_unknown_coverage"]:
        for item in coverage[section]:
            status = item.get("status") if isinstance(item, dict) else None
            if status not in STATUSES:
                raise ContestPackageCoverageError(f"Invalid coverage status: {status}")
