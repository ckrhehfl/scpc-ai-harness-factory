from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import json
import re

from factory.evidence_model import validate_evidence_index
from factory.requirement_model import (
    SCHEMA_VERSION,
    RequirementModelError,
    build_requirements_artifact,
    validate_requirements_artifact,
)
from factory.utils import to_simple_yaml


GOVERNANCE_PATHS = [
    "rules.allowed_language",
    "rules.external_api_allowed",
    "rules.external_data_allowed",
    "rules.pretrained_model_allowed",
    "rules.internet_allowed",
    "rules.manual_labeling_allowed",
    "rules.leakage_policy",
    "problem.evaluation_metric",
    "output.value_constraints",
]
HIGH_RISK_GOVERNANCE_PATHS = {
    "rules.external_api_allowed",
    "rules.external_data_allowed",
    "rules.pretrained_model_allowed",
    "rules.internet_allowed",
    "rules.leakage_policy",
    "problem.evaluation_metric",
    "output.value_constraints",
}
RED_NOT_MODELED_TOPICS = {
    "finalist code deliverable",
    "finalist presentation deliverable",
    "legal/IP terms",
}
TOKEN_SAFE_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")


def load_json(path: str | Path, label: str) -> dict[str, Any]:
    artifact_path = Path(path)
    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RequirementModelError(f"Malformed JSON in {label}: {exc}") from exc
    except OSError as exc:
        raise RequirementModelError(f"Could not read {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise RequirementModelError(f"{label} must be a JSON object")
    return data


def load_contest_spec(path: str | Path) -> dict[str, Any]:
    spec = load_json(path, "contest_spec.json")
    _validate_contest_spec(spec)
    return spec


def load_evidence_index(path: str | Path) -> dict[str, Any]:
    index = load_json(path, "evidence_index.json")
    validate_evidence_index(index)
    return index


def load_coverage(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    coverage = load_json(path, "contest_package_coverage.json")
    _validate_coverage(coverage)
    return coverage


def build_contest_requirements(
    contest_spec: dict[str, Any],
    evidence_index: dict[str, Any],
    *,
    coverage: dict[str, Any] | None = None,
    source_artifacts: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    _validate_contest_spec(contest_spec)
    validate_evidence_index(evidence_index)
    if coverage is not None:
        _validate_coverage(coverage)

    evidence = _EvidenceLookup(evidence_index)
    overrides = _applied_override_paths(contest_spec)
    conflicts = _coverage_conflict_paths(coverage)
    requirements: list[dict[str, Any]] = []
    warnings: list[str] = []

    requirements.extend(_core_requirements(contest_spec, evidence, warnings))
    requirements.extend(_governance_requirements(contest_spec, overrides, conflicts))
    if coverage:
        coverage_requirements, coverage_warnings = _coverage_requirements(coverage)
        requirements.extend(coverage_requirements)
        warnings.extend(coverage_warnings)

    artifact = build_requirements_artifact(
        requirements,
        source_artifacts=source_artifacts or {"contest_spec": None, "evidence_index": None, "coverage": None},
        warnings=warnings,
    )
    validate_requirements_artifact(artifact)
    return artifact


def render_contest_requirements_markdown(artifact: dict[str, Any]) -> str:
    validate_requirements_artifact(artifact)
    requirements = artifact["requirements"]
    summary = artifact["summary"]
    applicability = Counter(item["applicability"] for item in requirements)
    priority = Counter(item["priority"] for item in requirements)
    risk = Counter(item["risk_level"] for item in requirements)
    lines = [
        "# Contest Requirements",
        "",
        "Capability match는 현재 Registry의 token과 코드 근거를 비교한 기계적 결과다.",
        "공식 규칙 확인, solver 성능, Human Approval 또는 최종 제출 가능 여부를 보장하지 않는다.",
        "",
        "## Summary",
        "",
        f"- total: {summary['total']}",
        f"- active: {summary['active']}",
        f"- pending: {summary['pending']}",
        f"- not_modeled: {summary['not_modeled']}",
        f"- must: {summary['must']}",
        f"- red: {summary['red']}",
        "",
        "## Applicability",
        "",
    ]
    for key in ["active", "pending", "not_modeled"]:
        lines.append(f"- {key}: {applicability[key]}")
    lines.extend(["", "## Priority", ""])
    for key in ["must", "should", "informational"]:
        lines.append(f"- {key}: {priority[key]}")
    lines.extend(["", "## Risk", ""])
    for key in ["green", "yellow", "red"]:
        lines.append(f"- {key}: {risk[key]}")
    lines.extend(["", "## Requirements", ""])
    for requirement in requirements:
        lines.extend(
            [
                f"### {requirement['requirement_id']}",
                "",
                f"- title: {requirement['title']}",
                f"- origin: {requirement['origin']}",
                f"- domain: {requirement['domain']}",
                f"- type: {requirement['requirement_type']}",
                f"- priority: {requirement['priority']}",
                f"- provenance_status: {requirement['provenance_status']}",
                f"- applicability: {requirement['applicability']}",
                f"- risk_level: {requirement['risk_level']}",
                "- required_tokens:",
                _bullet(requirement["required_tokens"]),
                "- source_refs:",
                _yaml_block(requirement["source_refs"]),
                "- evidence_ids:",
                _bullet(requirement["evidence_ids"]),
                "- parameters:",
                _yaml_block(requirement["parameters"]),
                "- notes:",
                _bullet(requirement["notes"]),
                "",
            ]
        )
    if artifact["warnings"]:
        lines.extend(["## Warnings", "", _bullet(artifact["warnings"]), ""])
    return "\n".join(lines).rstrip() + "\n"


def _core_requirements(
    spec: dict[str, Any],
    evidence: "_EvidenceLookup",
    warnings: list[str],
) -> list[dict[str, Any]]:
    reqs: list[dict[str, Any]] = []
    test_exists = bool(_get_path(spec, "files.test.exists")[1])
    required_file = _get_path(spec, "output.required_file")[1]
    required_columns = _get_path(spec, "output.required_columns")[1]
    id_column = _get_path(spec, "output.id_column")[1]
    target_column = _get_path(spec, "output.target_column")[1]
    value_constraints = _get_path(spec, "output.value_constraints")[1]
    test_ids = evidence.ids_for("test.csv", {"inventory", "csv_structure"})
    sample_ids = evidence.ids_for("sample_submission.csv", {"inventory", "csv_structure"})

    if test_exists:
        reqs.append(
            _req(
                "req.runtime.test_csv_loading",
                "Load the contest test CSV",
                "contest_spec",
                "runtime",
                "capability",
                "must",
                "observed",
                "active",
                "green",
                ["harness.test_csv.load"],
                {"required_file": "test.csv"},
                [_ref("contest_spec.json", "files.test.exists")],
                test_ids,
            )
        )
        reqs.append(
            _req(
                "req.runtime.prediction_rows",
                "Emit one prediction row per test row",
                "contest_spec",
                "runtime",
                "capability",
                "must",
                "observed",
                "active",
                "green",
                ["harness.prediction.rows.emit"],
                {"scope": "row emission only"},
                [_ref("contest_spec.json", "files.test.exists")],
                test_ids,
            )
        )
        reqs.append(
            _req(
                "req.verification.submission_row_count",
                "Verify submission row count against test rows",
                "contest_spec",
                "verification",
                "capability",
                "must",
                "observed",
                "active",
                "green",
                ["submission.row_count.verify"],
                {"source_file": "test.csv"},
                [_ref("contest_spec.json", "files.test.exists")],
                test_ids,
            )
        )

    task_type = _get_path(spec, "problem.task_type")[1]
    if _is_unknown(task_type):
        reqs.append(
            _req(
                "req.solver.task_solution",
                "Provide a task-specific solver",
                "contest_spec",
                "solver",
                "unresolved",
                "must",
                "unknown",
                "pending",
                "red",
                [],
                {"task_type": task_type},
                [_ref("contest_spec.json", "problem.task_type")],
                [],
                ["Task type is unknown; no task-specific solver token can be derived."],
            )
        )
    else:
        normalized = _normalize_task_type(str(task_type))
        token = {
            "classification": "solver.classification.predict",
            "multiple_choice": "solver.multiple_choice.predict",
        }.get(normalized, f"solver.{normalized}.predict")
        if not TOKEN_SAFE_RE.match(token):
            warnings.append(f"Unsafe task_type token could not be modeled: {task_type}")
            reqs.append(
                _req(
                    "req.solver.task_solution",
                    "Provide a task-specific solver",
                    "contest_spec",
                    "solver",
                    "unresolved",
                    "must",
                    "unknown",
                    "pending",
                    "red",
                    [],
                    {"task_type": task_type, "normalized_task_type": normalized},
                    [_ref("contest_spec.json", "problem.task_type")],
                    [],
                    ["Normalized task type is not a safe dotted lowercase token component."],
                )
            )
        else:
            reqs.append(
                _req(
                    "req.solver.task_solution",
                    "Provide a task-specific solver",
                    "contest_spec",
                    "solver",
                    "capability",
                    "must",
                    "inferred",
                    "active",
                    "red",
                    [token],
                    {"task_type": task_type, "baseline_token_excluded": "harness.baseline.constant.predict"},
                    [_ref("contest_spec.json", "problem.task_type")],
                    [],
                    ["Constant baseline prediction is not a task-specific solver capability."],
                )
            )

    if not _is_unknown(required_file):
        reqs.append(
            _req(
                "req.output.submission_csv_writing",
                "Write the required submission CSV",
                "contest_spec",
                "output",
                "capability",
                "must",
                "observed",
                "active",
                "green",
                ["submission.csv.write"],
                {"required_file": required_file},
                [_ref("contest_spec.json", "output.required_file")],
                sample_ids,
            )
        )

    if isinstance(required_columns, list) and required_columns:
        reqs.append(
            _req(
                "req.output.submission_column_order",
                "Write submission columns in required order",
                "contest_spec",
                "output",
                "capability",
                "must",
                "observed",
                "active",
                "green",
                ["submission.columns.order"],
                {"required_columns": required_columns},
                [_ref("contest_spec.json", "output.required_columns")],
                sample_ids,
            )
        )
        reqs.append(
            _req(
                "req.verification.submission_schema",
                "Verify submission schema",
                "contest_spec",
                "verification",
                "capability",
                "must",
                "observed",
                "active",
                "green",
                ["submission.schema.verify"],
                {"required_columns": required_columns},
                [_ref("contest_spec.json", "output.required_columns")],
                sample_ids,
            )
        )

    if not _is_unknown(id_column):
        reqs.append(
            _req(
                "req.verification.submission_id_values",
                "Verify submission ID values",
                "contest_spec",
                "verification",
                "capability",
                "must",
                "inferred",
                "active",
                "green",
                ["submission.id_values.verify"],
                {"id_column": id_column},
                [_ref("contest_spec.json", "output.id_column")],
                sample_ids,
            )
        )

    if not _is_unknown(target_column):
        notes = []
        if _is_unknown(value_constraints):
            notes.append("output.value_constraints is unknown; target value domain cannot be fully verified.")
        reqs.append(
            _req(
                "req.verification.submission_target_values",
                "Verify submission target values",
                "contest_spec",
                "verification",
                "capability",
                "must",
                "inferred",
                "active",
                "yellow" if notes else "green",
                ["submission.target_values.verify"],
                {"target_column": target_column, "value_constraints": value_constraints},
                [_ref("contest_spec.json", "output.target_column"), _ref("contest_spec.json", "output.value_constraints")],
                sample_ids,
                notes,
            )
        )

    verification_active = any(
        req["requirement_id"].startswith("req.verification.") and req["applicability"] == "active"
        for req in reqs
    )
    if verification_active:
        reqs.append(
            _req(
                "req.verification.validation_report",
                "Write a local validation report",
                "factory_policy",
                "verification",
                "capability",
                "should",
                "proposed",
                "active",
                "green",
                ["submission.validation_report.write", "submission.validation_report.markdown"],
                {"scope": "local factory policy, not official approval"},
                [_ref("factory_policy", "local_validation_report")],
                [],
                ["Validation report is local evidence only and does not represent Human Approval."],
            )
        )
    return reqs


def _governance_requirements(
    spec: dict[str, Any],
    overrides: set[str],
    conflicts: set[str],
) -> list[dict[str, Any]]:
    reqs = []
    for path in GOVERNANCE_PATHS:
        exists, value = _get_path(spec, path)
        if path in conflicts:
            provenance = "conflicting"
            applicability = "pending"
            req_type = "unresolved"
        elif not exists or _is_unknown(value):
            provenance = "unknown"
            applicability = "pending"
            req_type = "unresolved"
        else:
            provenance = "confirmed" if path in overrides else "inferred"
            applicability = "active"
            req_type = _governance_type(path, value)
        reqs.append(
            _req(
                f"req.governance.{_path_to_id(path)}",
                f"Resolve governance rule {path}",
                "contest_spec",
                "governance",
                req_type,
                "must",
                provenance,
                applicability,
                "red" if path in HIGH_RISK_GOVERNANCE_PATHS else "yellow",
                [],
                {"path": path, "value": value if exists else None},
                [_ref("contest_spec.json", path)],
                [],
                ["Capability token matching cannot prove compliance for this rule."],
            )
        )
    return reqs


def _coverage_requirements(coverage: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    reqs: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item in coverage.get("high_risk_unknowns", []):
        path = item["path"]
        reqs.append(
            _req(
                f"req.coverage.high_risk.{_path_to_id(path)}",
                f"High-risk unknown remains unresolved: {path}",
                "coverage",
                "coverage",
                "unresolved",
                "must",
                "unknown",
                "pending",
                "red",
                [],
                dict(item),
                [_ref("contest_package_coverage.json", f"high_risk_unknowns.{path}")],
                [],
            )
        )
    for item in coverage.get("not_modeled_topics", []):
        topic = item["topic"]
        reqs.append(
            _req(
                f"req.coverage.not_modeled.{_topic_to_id(topic)}",
                f"Topic is not modeled: {topic}",
                "coverage",
                "coverage",
                "unresolved",
                "informational",
                "unknown",
                "not_modeled",
                "red" if topic in RED_NOT_MODELED_TOPICS else "yellow",
                [],
                dict(item),
                [_ref("contest_package_coverage.json", f"not_modeled_topics.{topic}")],
                [],
            )
        )
    for item in coverage.get("warnings", []):
        warnings.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
    return reqs, warnings


class _EvidenceLookup:
    def __init__(self, evidence_index: dict[str, Any]) -> None:
        self.records = evidence_index.get("records", [])

    def ids_for(self, source_file: str, types: set[str]) -> list[str]:
        ids = []
        for record in self.records:
            if record.get("source_file") != source_file:
                continue
            key = record.get("key", "")
            evidence_type = key.rsplit(":", 1)[-1]
            if evidence_type in types:
                ids.append(record["evidence_id"])
        return sorted(set(ids))


def _req(
    requirement_id: str,
    title: str,
    origin: str,
    domain: str,
    requirement_type: str,
    priority: str,
    provenance_status: str,
    applicability: str,
    risk_level: str,
    required_tokens: list[str],
    parameters: dict[str, Any],
    source_refs: list[dict[str, str]],
    evidence_ids: list[str],
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement_id,
        "title": title,
        "origin": origin,
        "domain": domain,
        "requirement_type": requirement_type,
        "priority": priority,
        "provenance_status": provenance_status,
        "applicability": applicability,
        "risk_level": risk_level,
        "required_tokens": sorted(required_tokens),
        "parameters": parameters,
        "source_refs": sorted(source_refs, key=lambda item: (item["artifact"], item["path"])),
        "evidence_ids": sorted(set(evidence_ids)),
        "notes": sorted(notes or []),
    }


def _ref(artifact: str, path: str) -> dict[str, str]:
    return {"artifact": artifact, "path": path}


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


def _normalize_task_type(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]+", "_", value.lower())).strip("_")


def _path_to_id(path: str) -> str:
    return _topic_to_id(path.replace(".", "_"))


def _topic_to_id(topic: str) -> str:
    normalized = re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]+", "_", topic.lower())).strip("_")
    return normalized or "unknown"


def _applied_override_paths(spec: dict[str, Any]) -> set[str]:
    applied = spec.get("decision_overrides", {}).get("applied", [])
    if not isinstance(applied, list):
        return set()
    return {item["item"] for item in applied if isinstance(item, dict) and isinstance(item.get("item"), str)}


def _coverage_conflict_paths(coverage: dict[str, Any] | None) -> set[str]:
    if not coverage:
        return set()
    paths = set()
    for item in coverage.get("declared_unknown_coverage", []):
        if isinstance(item, dict) and item.get("status") == "conflicting" and isinstance(item.get("path"), str):
            paths.add(item["path"])
    return paths


def _governance_type(path: str, value: Any) -> str:
    if path == "rules.leakage_policy" and str(value).lower() == "strict":
        return "prohibition"
    if path.startswith("rules.") and str(value).lower() in {"false", "not_allowed", "disallowed", "no"}:
        return "prohibition"
    return "constraint"


def _validate_contest_spec(spec: dict[str, Any]) -> None:
    if not isinstance(spec.get("files"), dict):
        raise RequirementModelError("contest_spec.files must be an object")
    if not isinstance(spec.get("problem"), dict):
        raise RequirementModelError("contest_spec.problem must be an object")
    if not isinstance(spec.get("rules"), dict):
        raise RequirementModelError("contest_spec.rules must be an object")
    if not isinstance(spec.get("output"), dict):
        raise RequirementModelError("contest_spec.output must be an object")


def _validate_coverage(coverage: dict[str, Any]) -> None:
    if coverage.get("schema_version") != "v0.9B":
        raise RequirementModelError("Invalid coverage schema_version")
    if coverage.get("artifact_type") != "contest_package_coverage":
        raise RequirementModelError("Invalid coverage artifact_type")
    for field in ["high_risk_unknowns", "not_modeled_topics", "warnings"]:
        if not isinstance(coverage.get(field), list):
            raise RequirementModelError(f"coverage.{field} must be a list")


def _bullet(items: list[str]) -> str:
    if not items:
        return "  - none"
    return "\n".join(f"  - `{item}`" for item in items)


def _yaml_block(value: Any) -> str:
    return "\n".join(["  ```yaml", _indent(to_simple_yaml(value), "  "), "  ```"])


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else prefix for line in text.splitlines())
