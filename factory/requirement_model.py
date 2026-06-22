from __future__ import annotations

from collections import Counter
from typing import Any
import json
import re

from factory.utils import write_json, write_text


SCHEMA_VERSION = "v0.10B"
REQUIREMENTS_ARTIFACT_TYPE = "contest_requirements"
MATCH_ARTIFACT_TYPE = "requirement_capability_match"

REQUIREMENT_ID_RE = re.compile(r"^req\.[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
TOKEN_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
EVIDENCE_ID_RE = re.compile(r"^ev_[0-9a-f]{16}$")

ORIGINS = {"contest_spec", "factory_policy", "coverage"}
DOMAINS = {"input", "runtime", "solver", "output", "verification", "governance", "handoff", "coverage"}
REQUIREMENT_TYPES = {"capability", "constraint", "prohibition", "unresolved"}
PRIORITIES = {"must", "should", "informational"}
PROVENANCE_STATUSES = {"observed", "inferred", "proposed", "confirmed", "unknown", "conflicting"}
APPLICABILITIES = {"active", "pending", "not_modeled"}
RISK_LEVELS = {"green", "yellow", "red"}
MATCH_STATUSES = {"satisfied", "partial", "unmet", "blocked", "not_evaluated", "not_applicable"}
SOURCE_REF_ARTIFACTS = {"contest_spec.json", "evidence_index.json", "contest_package_coverage.json", "factory_policy"}


class RequirementModelError(ValueError):
    pass


def validate_requirement_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        raise RequirementModelError("Requirement record must be an object")
    required = [
        "requirement_id",
        "title",
        "origin",
        "domain",
        "requirement_type",
        "priority",
        "provenance_status",
        "applicability",
        "risk_level",
        "required_tokens",
        "parameters",
        "source_refs",
        "evidence_ids",
        "notes",
    ]
    _require_fields(record, required, "requirement")

    requirement_id = _non_empty_string(record["requirement_id"], "requirement_id")
    if not REQUIREMENT_ID_RE.match(requirement_id):
        raise RequirementModelError(f"Invalid requirement_id: {requirement_id}")
    _non_empty_string(record["title"], f"{requirement_id}.title")
    _one_of(record["origin"], ORIGINS, f"{requirement_id}.origin")
    _one_of(record["domain"], DOMAINS, f"{requirement_id}.domain")
    requirement_type = _one_of(record["requirement_type"], REQUIREMENT_TYPES, f"{requirement_id}.requirement_type")
    _one_of(record["priority"], PRIORITIES, f"{requirement_id}.priority")
    _one_of(record["provenance_status"], PROVENANCE_STATUSES, f"{requirement_id}.provenance_status")
    _one_of(record["applicability"], APPLICABILITIES, f"{requirement_id}.applicability")
    _one_of(record["risk_level"], RISK_LEVELS, f"{requirement_id}.risk_level")

    tokens = _string_list(record["required_tokens"], f"{requirement_id}.required_tokens")
    if requirement_type == "capability" and not tokens:
        raise RequirementModelError(f"{requirement_id} capability requirement must include required_tokens")
    _validate_unique(tokens, f"{requirement_id}.required_tokens")
    for token in tokens:
        if not TOKEN_RE.match(token):
            raise RequirementModelError(f"Invalid required token for {requirement_id}: {token}")

    if not isinstance(record["parameters"], dict):
        raise RequirementModelError(f"{requirement_id}.parameters must be an object")
    _ensure_json_serializable(record["parameters"], f"{requirement_id}.parameters")

    refs = record["source_refs"]
    if not isinstance(refs, list):
        raise RequirementModelError(f"{requirement_id}.source_refs must be a list")
    for index, ref in enumerate(refs):
        validate_source_ref(ref, f"{requirement_id}.source_refs[{index}]")

    evidence_ids = _string_list(record["evidence_ids"], f"{requirement_id}.evidence_ids")
    _validate_unique(evidence_ids, f"{requirement_id}.evidence_ids")
    for evidence_id in evidence_ids:
        if not EVIDENCE_ID_RE.match(evidence_id):
            raise RequirementModelError(f"Invalid evidence_id for {requirement_id}: {evidence_id}")

    notes = _string_list(record["notes"], f"{requirement_id}.notes")
    for note in notes:
        if not note.strip():
            raise RequirementModelError(f"{requirement_id}.notes must contain non-empty strings")


def validate_source_ref(ref: Any, context: str) -> None:
    if not isinstance(ref, dict):
        raise RequirementModelError(f"{context} must be an object")
    _require_fields(ref, ["artifact", "path"], context)
    artifact = _one_of(ref["artifact"], SOURCE_REF_ARTIFACTS, f"{context}.artifact")
    path = _non_empty_string(ref["path"], f"{context}.path")
    if artifact != "factory_policy" and path == "factory_policy":
        raise RequirementModelError(f"{context}.path must identify a source path")


def build_requirement_summary(requirements: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(item["applicability"] for item in requirements)
    priorities = Counter(item["priority"] for item in requirements)
    risks = Counter(item["risk_level"] for item in requirements)
    return {
        "total": len(requirements),
        "active": counts["active"],
        "pending": counts["pending"],
        "not_modeled": counts["not_modeled"],
        "must": priorities["must"],
        "red": risks["red"],
    }


def build_requirements_artifact(
    requirements: list[dict[str, Any]],
    *,
    source_artifacts: dict[str, str | None],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    for requirement in requirements:
        validate_requirement_record(requirement)
    ids = [item["requirement_id"] for item in requirements]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise RequirementModelError(f"Duplicate requirement_id(s): {', '.join(duplicates)}")
    ordered = sorted(requirements, key=lambda item: item["requirement_id"])
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": REQUIREMENTS_ARTIFACT_TYPE,
        "source_artifacts": {
            "contest_spec": source_artifacts.get("contest_spec"),
            "evidence_index": source_artifacts.get("evidence_index"),
            "coverage": source_artifacts.get("coverage"),
        },
        "summary": build_requirement_summary(ordered),
        "requirements": ordered,
        "warnings": sorted(warnings or []),
    }
    validate_requirements_artifact(artifact)
    return artifact


def validate_requirements_artifact(artifact: dict[str, Any]) -> None:
    if not isinstance(artifact, dict):
        raise RequirementModelError("Requirements artifact must be an object")
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise RequirementModelError("Invalid requirements schema_version")
    if artifact.get("artifact_type") != REQUIREMENTS_ARTIFACT_TYPE:
        raise RequirementModelError("Invalid requirements artifact_type")
    requirements = artifact.get("requirements")
    if not isinstance(requirements, list):
        raise RequirementModelError("requirements must be a list")
    ids = []
    for requirement in requirements:
        validate_requirement_record(requirement)
        ids.append(requirement["requirement_id"])
    if ids != sorted(ids):
        raise RequirementModelError("requirements must be sorted by requirement_id")
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise RequirementModelError(f"Duplicate requirement_id(s): {', '.join(duplicates)}")
    if artifact.get("summary") != build_requirement_summary(requirements):
        raise RequirementModelError("Requirement summary does not match records")
    _string_list(artifact.get("warnings"), "warnings")


def validate_match_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        raise RequirementModelError("Match record must be an object")
    _require_fields(
        record,
        [
            "requirement_id",
            "match_status",
            "required_tokens",
            "token_matches",
            "matched_capability_ids",
            "dependency_capability_ids",
            "missing_tokens",
            "blocked_by",
            "notes",
        ],
        "match",
    )
    requirement_id = _non_empty_string(record["requirement_id"], "match.requirement_id")
    if not REQUIREMENT_ID_RE.match(requirement_id):
        raise RequirementModelError(f"Invalid match requirement_id: {requirement_id}")
    _one_of(record["match_status"], MATCH_STATUSES, f"{requirement_id}.match_status")
    for field in ["required_tokens", "matched_capability_ids", "dependency_capability_ids", "missing_tokens", "blocked_by", "notes"]:
        _validate_unique(_string_list(record[field], f"{requirement_id}.{field}"), f"{requirement_id}.{field}")
    for item in record["token_matches"]:
        if not isinstance(item, dict):
            raise RequirementModelError(f"{requirement_id}.token_matches entries must be objects")
        _require_fields(
            item,
            [
                "token",
                "eligible_capability_ids",
                "limited_capability_ids",
                "ineligible_capability_ids",
                "blocked_capability_ids",
            ],
            f"{requirement_id}.token_matches",
        )
        token = _non_empty_string(item["token"], f"{requirement_id}.token")
        if not TOKEN_RE.match(token):
            raise RequirementModelError(f"Invalid token in match: {token}")
        for field in ["eligible_capability_ids", "limited_capability_ids", "ineligible_capability_ids", "blocked_capability_ids"]:
            values = _string_list(item[field], f"{requirement_id}.{token}.{field}")
            if values != sorted(values):
                raise RequirementModelError(f"{requirement_id}.{token}.{field} must be sorted")


def build_match_summary(requirements: list[dict[str, Any]], matches: list[dict[str, Any]]) -> dict[str, int]:
    by_id = {match["requirement_id"]: match for match in matches}
    counts = Counter(match["match_status"] for match in matches)
    return {
        "total": len(matches),
        "satisfied": counts["satisfied"],
        "partial": counts["partial"],
        "unmet": counts["unmet"],
        "blocked": counts["blocked"],
        "not_evaluated": counts["not_evaluated"],
        "not_applicable": counts["not_applicable"],
        "active_must_gap_count": sum(
            1
            for requirement in requirements
            if requirement["priority"] == "must"
            and requirement["applicability"] == "active"
            and by_id[requirement["requirement_id"]]["match_status"] in {"partial", "unmet", "blocked"}
        ),
        "pending_high_risk_count": sum(
            1 for requirement in requirements if requirement["risk_level"] == "red" and requirement["applicability"] == "pending"
        ),
    }


def validate_match_artifact(artifact: dict[str, Any], requirements: list[dict[str, Any]] | None = None) -> None:
    if not isinstance(artifact, dict):
        raise RequirementModelError("Match artifact must be an object")
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise RequirementModelError("Invalid match schema_version")
    if artifact.get("artifact_type") != MATCH_ARTIFACT_TYPE:
        raise RequirementModelError("Invalid match artifact_type")
    matches = artifact.get("matches")
    if not isinstance(matches, list):
        raise RequirementModelError("matches must be a list")
    ids = []
    for match in matches:
        validate_match_record(match)
        ids.append(match["requirement_id"])
    if ids != sorted(ids):
        raise RequirementModelError("matches must be sorted by requirement_id")
    if requirements is not None and artifact.get("summary") != build_match_summary(requirements, matches):
        raise RequirementModelError("Match summary does not match records")
    _string_list(artifact.get("unmatched_tokens"), "unmatched_tokens")
    _string_list(artifact.get("warnings"), "warnings")


def save_requirements_artifact(artifact: dict[str, Any], output_dir: str | Any, markdown: str) -> dict[str, Any]:
    validate_requirements_artifact(artifact)
    from pathlib import Path

    out = Path(output_dir)
    return {
        "json": write_json(out / "contest_requirements.json", artifact),
        "md": write_text(out / "contest_requirements.md", markdown),
    }


def save_match_artifact(artifact: dict[str, Any], output_dir: str | Any, markdown: str, requirements: list[dict[str, Any]]) -> dict[str, Any]:
    validate_match_artifact(artifact, requirements)
    from pathlib import Path

    out = Path(output_dir)
    return {
        "json": write_json(out / "requirement_capability_match.json", artifact),
        "md": write_text(out / "requirement_capability_match.md", markdown),
    }


def _require_fields(mapping: dict[str, Any], fields: list[str], context: str) -> None:
    missing = [field for field in fields if field not in mapping]
    if missing:
        raise RequirementModelError(f"{context} is missing fields: {', '.join(missing)}")


def _non_empty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RequirementModelError(f"{context} must be a non-empty string")
    return value


def _one_of(value: Any, allowed: set[str], context: str) -> str:
    text = _non_empty_string(value, context)
    if text not in allowed:
        raise RequirementModelError(f"Invalid {context}: {text}")
    return text


def _string_list(value: Any, context: str) -> list[str]:
    if not isinstance(value, list):
        raise RequirementModelError(f"{context} must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise RequirementModelError(f"{context}[{index}] must be a non-empty string")
    return value


def _validate_unique(items: list[str], context: str) -> None:
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise RequirementModelError(f"{context} contains duplicate value(s): {', '.join(duplicates)}")


def _ensure_json_serializable(value: Any, context: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RequirementModelError(f"{context} must be JSON serializable: {exc}") from exc
