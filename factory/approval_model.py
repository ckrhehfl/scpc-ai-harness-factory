from __future__ import annotations

from typing import Any
import copy
import re

from factory.decision_model import canonical_json_digest


SCHEMA_VERSION = "v0.11B"
APPROVAL_INTAKE_ARTIFACT_TYPE = "human_approval_intake"
APPROVAL_SUMMARY_ARTIFACT_TYPE = "human_approval_summary"
APPROVAL_SCOPE = "local_submission_candidate"

APPROVAL_ID_RE = re.compile(r"^approval\.local_submission_candidate\.r[0-9]{3}$")
GATE_CHECK_ID_RE = re.compile(r"^gate\.[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

APPROVAL_STATUSES = {"pending", "approved", "rejected", "conditional"}
HUMAN_APPROVAL_STATUSES = {
    "not_provided",
    "pending",
    "approved",
    "rejected",
    "conditional",
    "stale",
    "conflicting",
}
MACHINE_READINESS_STATUSES = {"blocked", "reviewable"}
OVERALL_GATE_STATUSES = {
    "blocked",
    "awaiting_human_approval",
    "approved",
    "rejected",
    "conditional_approval",
    "stale_approval",
    "conflicting_approval",
}
GATE_CHECK_STATUSES = {"pass", "fail", "warning"}
GATE_CHECK_SEVERITIES = {"blocker", "warning", "informational"}

SOURCE_DIGEST_KEYS = [
    "contest_requirements",
    "requirement_capability_match",
    "decision_ledger",
    "capability_registry",
    "validation_report",
]


class ApprovalModelError(ValueError):
    pass


def validate_approval_entry(entry: dict[str, Any]) -> None:
    if not isinstance(entry, dict):
        raise ApprovalModelError("Approval entry must be an object")
    _require_fields(
        entry,
        [
            "approval_id",
            "scope",
            "expected_readiness_digest",
            "actor",
            "approval_status",
            "rationale",
            "conditions",
            "supersedes",
            "notes",
        ],
        "approval",
    )
    approval_id = _approval_id(entry["approval_id"])
    if _revision(approval_id) < 1:
        raise ApprovalModelError(f"{approval_id}: revision must be 001 or greater")
    if entry["scope"] != APPROVAL_SCOPE:
        raise ApprovalModelError(f"{approval_id}: unsupported scope {entry['scope']}")
    _digest(entry["expected_readiness_digest"], f"{approval_id}.expected_readiness_digest")
    if entry["actor"] != "human":
        raise ApprovalModelError(f"{approval_id}: actor must be human")
    status = _one_of(entry["approval_status"], APPROVAL_STATUSES, f"{approval_id}.approval_status")
    rationale = entry["rationale"]
    if not isinstance(rationale, str):
        raise ApprovalModelError(f"{approval_id}.rationale must be a string")
    conditions = _string_list(entry["conditions"], f"{approval_id}.conditions")
    notes = _string_list(entry["notes"], f"{approval_id}.notes")
    _validate_unique(conditions, f"{approval_id}.conditions")
    _validate_unique(notes, f"{approval_id}.notes")
    supersedes = entry["supersedes"]
    if supersedes is not None:
        _approval_id(supersedes)

    if status == "pending":
        if conditions:
            raise ApprovalModelError(f"{approval_id}: pending approval must not include conditions")
        return
    if not rationale.strip():
        raise ApprovalModelError(f"{approval_id}: {status} approval requires rationale")
    if status in {"approved", "rejected"} and conditions:
        raise ApprovalModelError(f"{approval_id}: {status} approval must not include conditions")
    if status == "conditional" and not conditions:
        raise ApprovalModelError(f"{approval_id}: conditional approval requires conditions")


def validate_approval_intake(
    intake: dict[str, Any],
    *,
    known_approval_ids: set[str] | None = None,
) -> None:
    if not isinstance(intake, dict):
        raise ApprovalModelError("Human approval intake must be an object")
    if intake.get("schema_version") != SCHEMA_VERSION:
        raise ApprovalModelError("Invalid human approval intake schema_version")
    if intake.get("artifact_type") != APPROVAL_INTAKE_ARTIFACT_TYPE:
        raise ApprovalModelError("Invalid human approval intake artifact_type")
    source_digests = intake.get("source_digests")
    if not isinstance(source_digests, dict):
        raise ApprovalModelError("source_digests must be an object")
    for key in SOURCE_DIGEST_KEYS:
        value = source_digests.get(key)
        if key == "validation_report" and value is None:
            continue
        _digest(value, f"source_digests.{key}")
    _digest(intake.get("readiness_digest"), "readiness_digest")
    notes = _string_list(intake.get("notes"), "notes")
    _validate_unique(notes, "notes")
    approvals = intake.get("approvals")
    if not isinstance(approvals, list):
        raise ApprovalModelError("approvals must be a list")

    by_id: dict[str, dict[str, Any]] = {}
    for entry in approvals:
        validate_approval_entry(entry)
        approval_id = entry["approval_id"]
        if approval_id in by_id:
            raise ApprovalModelError(f"Duplicate approval_id: {approval_id}")
        by_id[approval_id] = entry

    known_approval_ids = known_approval_ids or set()
    for entry in approvals:
        supersedes = entry["supersedes"]
        if supersedes is None:
            continue
        approval_id = entry["approval_id"]
        if supersedes not in by_id and supersedes not in known_approval_ids:
            raise ApprovalModelError(f"{approval_id} supersedes unknown approval_id {supersedes}")
        if supersedes == approval_id:
            raise ApprovalModelError(f"{approval_id} must not supersede itself")
        parent = by_id.get(supersedes)
        if parent is not None and parent["scope"] != entry["scope"]:
            raise ApprovalModelError(f"{approval_id} supersedes a different scope")
        if _revision(approval_id) <= _revision(supersedes):
            raise ApprovalModelError(f"{approval_id} revision must be greater than superseded revision")
    _validate_supersession_cycles(by_id)


def validate_gate_check(check: dict[str, Any]) -> None:
    if not isinstance(check, dict):
        raise ApprovalModelError("Gate check must be an object")
    _require_fields(
        check,
        [
            "check_id",
            "category",
            "status",
            "severity",
            "observed",
            "expected",
            "related_requirement_ids",
            "related_capability_ids",
            "notes",
        ],
        "gate_check",
    )
    check_id = check["check_id"]
    if not isinstance(check_id, str) or not GATE_CHECK_ID_RE.match(check_id):
        raise ApprovalModelError(f"Invalid gate check_id: {check_id}")
    if not isinstance(check["category"], str) or not check["category"].strip():
        raise ApprovalModelError(f"{check_id}.category must be a non-empty string")
    _one_of(check["status"], GATE_CHECK_STATUSES, f"{check_id}.status")
    _one_of(check["severity"], GATE_CHECK_SEVERITIES, f"{check_id}.severity")
    for field in ["related_requirement_ids", "related_capability_ids", "notes"]:
        values = _string_list(check[field], f"{check_id}.{field}")
        if values != sorted(set(values)):
            raise ApprovalModelError(f"{check_id}.{field} must be sorted and unique")


def validate_human_approval_summary(summary: dict[str, Any]) -> None:
    if not isinstance(summary, dict):
        raise ApprovalModelError("Human approval summary must be an object")
    if summary.get("schema_version") != SCHEMA_VERSION:
        raise ApprovalModelError("Invalid human approval summary schema_version")
    if summary.get("artifact_type") != APPROVAL_SUMMARY_ARTIFACT_TYPE:
        raise ApprovalModelError("Invalid human approval summary artifact_type")
    if summary.get("scope") != APPROVAL_SCOPE:
        raise ApprovalModelError("Invalid human approval summary scope")
    for key in SOURCE_DIGEST_KEYS:
        value = summary.get("source_digests", {}).get(key)
        if key == "validation_report" and value is None:
            continue
        _digest(value, f"source_digests.{key}")
    _digest(summary.get("readiness_digest"), "readiness_digest")

    machine = summary.get("machine_readiness")
    if not isinstance(machine, dict):
        raise ApprovalModelError("machine_readiness must be an object")
    _one_of(machine.get("status"), MACHINE_READINESS_STATUSES, "machine_readiness.status")
    if not isinstance(machine.get("blocker_count"), int) or machine["blocker_count"] < 0:
        raise ApprovalModelError("machine_readiness.blocker_count must be a non-negative int")
    if not isinstance(machine.get("warning_count"), int) or machine["warning_count"] < 0:
        raise ApprovalModelError("machine_readiness.warning_count must be a non-negative int")
    checks = machine.get("checks")
    if not isinstance(checks, list):
        raise ApprovalModelError("machine_readiness.checks must be a list")
    for check in checks:
        validate_gate_check(check)

    human = summary.get("human_approval")
    if not isinstance(human, dict):
        raise ApprovalModelError("human_approval must be an object")
    _one_of(human.get("status"), HUMAN_APPROVAL_STATUSES, "human_approval.status")
    if not isinstance(human.get("authoritative"), bool):
        raise ApprovalModelError("human_approval.authoritative must be a bool")
    if not isinstance(human.get("approval_granted"), bool):
        raise ApprovalModelError("human_approval.approval_granted must be a bool")
    current_id = human.get("current_approval_id")
    if current_id is not None:
        _approval_id(current_id)
    if not isinstance(human.get("history"), list):
        raise ApprovalModelError("human_approval.history must be a list")
    _string_list(human.get("warnings"), "human_approval.warnings")

    gate = summary.get("overall_gate")
    if not isinstance(gate, dict):
        raise ApprovalModelError("overall_gate must be an object")
    _one_of(gate.get("status"), OVERALL_GATE_STATUSES, "overall_gate.status")
    if gate.get("exit_code") not in {0, 2}:
        raise ApprovalModelError("overall_gate.exit_code must be 0 or 2")
    _string_list(gate.get("blocking_check_ids"), "overall_gate.blocking_check_ids")
    if not isinstance(gate.get("statement"), str):
        raise ApprovalModelError("overall_gate.statement must be a string")


def build_readiness_digest(
    source_digests: dict[str, str | None],
    machine_readiness: dict[str, Any],
) -> str:
    normalized_sources = {key: source_digests.get(key) for key in SOURCE_DIGEST_KEYS}
    for key, value in normalized_sources.items():
        if key == "validation_report" and value is None:
            continue
        _digest(value, f"source_digests.{key}")
    payload = {
        "source_digests": normalized_sources,
        "machine_readiness": copy.deepcopy(machine_readiness),
    }
    return canonical_json_digest(payload)


def approval_revision(approval_id: str) -> int:
    return _revision(_approval_id(approval_id))


def _approval_id(value: Any) -> str:
    if not isinstance(value, str) or not APPROVAL_ID_RE.match(value):
        raise ApprovalModelError(f"Invalid approval_id: {value}")
    return value


def _revision(identifier: str) -> int:
    return int(identifier.rsplit("r", 1)[1])


def _digest(value: Any, context: str) -> str:
    if not isinstance(value, str) or not DIGEST_RE.match(value):
        raise ApprovalModelError(f"{context} must be a sha256 digest")
    return value


def _one_of(value: Any, allowed: set[str], context: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ApprovalModelError(f"{context} must be one of: {', '.join(sorted(allowed))}")
    return value


def _string_list(value: Any, context: str) -> list[str]:
    if not isinstance(value, list):
        raise ApprovalModelError(f"{context} must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ApprovalModelError(f"{context}[{index}] must be a non-empty string")
    return value


def _validate_unique(items: list[str], context: str) -> None:
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise ApprovalModelError(f"{context} contains duplicate value(s): {', '.join(duplicates)}")


def _require_fields(mapping: dict[str, Any], fields: list[str], context: str) -> None:
    missing = [field for field in fields if field not in mapping]
    if missing:
        raise ApprovalModelError(f"{context} missing required field(s): {', '.join(missing)}")


def _validate_supersession_cycles(by_id: dict[str, dict[str, Any]]) -> None:
    for approval_id in sorted(by_id):
        seen: set[str] = set()
        current = approval_id
        while current in by_id and by_id[current]["supersedes"] is not None:
            if current in seen:
                raise ApprovalModelError(f"Supersession cycle detected at {current}")
            seen.add(current)
            current = by_id[current]["supersedes"]
        if current in seen:
            raise ApprovalModelError(f"Supersession cycle detected at {current}")
