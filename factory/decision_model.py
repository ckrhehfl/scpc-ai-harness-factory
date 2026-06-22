from __future__ import annotations

from collections import Counter
from typing import Any
import hashlib
import json
import re


SCHEMA_VERSION = "v0.11A"
DECISION_INTAKE_ARTIFACT_TYPE = "decision_intake"
DECISION_LEDGER_ARTIFACT_TYPE = "decision_ledger"

DECISION_ID_RE = re.compile(r"^dec\.[a-z0-9_]+(?:\.[a-z0-9_]+)+\.r[0-9]{3}$")
REQUIREMENT_ID_RE = re.compile(r"^req\.[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EVIDENCE_ID_RE = re.compile(r"^ev_[0-9a-f]{16}$")

INTAKE_ACTORS = {"human", "ai"}
INTAKE_STATUSES = {"pending", "proposed", "confirmed", "rejected"}
LEDGER_STATUSES = {
    "not_required",
    "pending",
    "proposed",
    "confirmed",
    "rejected",
    "stale",
    "conflicting",
}
ACTIONS = {
    "no_action",
    "use_existing_capability",
    "implement_missing_capability",
    "confirm_value",
    "accept_risk",
    "wait_for_information",
    "waive_requirement",
    "reject_requirement",
}
FOLLOW_UP_ACTIONS = {"implement_missing_capability", "confirm_value", "wait_for_information"}
SOURCE_DIGEST_KEYS = ["contest_requirements", "requirement_capability_match", "capability_registry"]


class DecisionModelError(ValueError):
    pass


def canonical_json_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def build_subject_digest(requirement: dict[str, Any], match: dict[str, Any]) -> str:
    return canonical_json_digest({"requirement": requirement, "match": match})


def validate_decision_entry(entry: dict[str, Any]) -> None:
    if not isinstance(entry, dict):
        raise DecisionModelError("Decision entry must be an object")
    _require_fields(
        entry,
        [
            "decision_id",
            "requirement_id",
            "expected_subject_digest",
            "actor",
            "decision_status",
            "action",
            "decision_value",
            "rationale",
            "selected_capability_ids",
            "evidence_ids",
            "conditions",
            "supersedes",
            "notes",
        ],
        "decision",
    )
    decision_id = _decision_id(entry["decision_id"])
    requirement_id = _requirement_id(entry["requirement_id"])
    if _requirement_id_from_decision_id(decision_id) != requirement_id:
        raise DecisionModelError(f"{decision_id} does not match requirement_id {requirement_id}")
    _digest(entry["expected_subject_digest"], f"{decision_id}.expected_subject_digest")
    actor = _one_of(entry["actor"], INTAKE_ACTORS, f"{decision_id}.actor")
    status = _one_of(entry["decision_status"], INTAKE_STATUSES, f"{decision_id}.decision_status")
    action = _one_of(entry["action"], ACTIONS, f"{decision_id}.action")

    if actor == "ai" and status != "proposed":
        raise DecisionModelError(f"{decision_id}: ai actor may only use proposed status")
    if actor == "human" and status == "proposed":
        raise DecisionModelError(f"{decision_id}: human actor may not use proposed status")
    if status in {"confirmed", "rejected"} and actor != "human":
        raise DecisionModelError(f"{decision_id}: {status} decisions must be human")

    rationale = entry["rationale"]
    if not isinstance(rationale, str):
        raise DecisionModelError(f"{decision_id}.rationale must be a string")
    selected = _string_list(entry["selected_capability_ids"], f"{decision_id}.selected_capability_ids")
    evidence = _string_list(entry["evidence_ids"], f"{decision_id}.evidence_ids")
    conditions = _string_list(entry["conditions"], f"{decision_id}.conditions")
    notes = _string_list(entry["notes"], f"{decision_id}.notes")
    _validate_unique(selected, f"{decision_id}.selected_capability_ids")
    _validate_unique(evidence, f"{decision_id}.evidence_ids")
    _validate_unique(conditions, f"{decision_id}.conditions")
    _validate_unique(notes, f"{decision_id}.notes")
    for evidence_id in evidence:
        if not EVIDENCE_ID_RE.match(evidence_id):
            raise DecisionModelError(f"{decision_id}: invalid evidence_id {evidence_id}")
    supersedes = entry["supersedes"]
    if supersedes is not None:
        _decision_id(supersedes)

    value = entry["decision_value"]
    if status == "pending":
        if action != "no_action":
            raise DecisionModelError(f"{decision_id}: pending decisions must use no_action")
        if value is not None:
            raise DecisionModelError(f"{decision_id}: pending decisions must not include decision_value")
        if selected:
            raise DecisionModelError(f"{decision_id}: pending decisions must not select capabilities")
        return

    if action == "no_action":
        raise DecisionModelError(f"{decision_id}: non-pending decisions must not use no_action")
    if not rationale.strip():
        raise DecisionModelError(f"{decision_id}: non-pending decisions require rationale")

    if action == "use_existing_capability":
        if not selected:
            raise DecisionModelError(f"{decision_id}: use_existing_capability requires selected_capability_ids")
        if value is not None:
            raise DecisionModelError(f"{decision_id}: use_existing_capability must not include decision_value")
        return
    if action == "implement_missing_capability":
        _require_empty_selection_and_null_value(decision_id, selected, value, action)
        return
    if action == "confirm_value":
        if selected:
            raise DecisionModelError(f"{decision_id}: confirm_value must not select capabilities")
        if value is None or value == "" or value == "unknown":
            raise DecisionModelError(f"{decision_id}: confirm_value requires a known decision_value")
        _ensure_json_serializable(value, f"{decision_id}.decision_value")
        return

    _require_empty_selection_and_null_value(decision_id, selected, value, action)


def validate_decision_intake(intake: dict[str, Any], known_decision_ids: set[str] | None = None) -> None:
    if not isinstance(intake, dict):
        raise DecisionModelError("Decision intake must be an object")
    if intake.get("schema_version") != SCHEMA_VERSION:
        raise DecisionModelError("Invalid decision intake schema_version")
    if intake.get("artifact_type") != DECISION_INTAKE_ARTIFACT_TYPE:
        raise DecisionModelError("Invalid decision intake artifact_type")
    source_digests = intake.get("source_digests")
    if not isinstance(source_digests, dict):
        raise DecisionModelError("source_digests must be an object")
    for key in SOURCE_DIGEST_KEYS:
        _digest(source_digests.get(key), f"source_digests.{key}")

    decisions = intake.get("decisions")
    if not isinstance(decisions, list):
        raise DecisionModelError("decisions must be a list")
    notes = _string_list(intake.get("notes"), "notes")
    _validate_unique(notes, "notes")

    by_id: dict[str, dict[str, Any]] = {}
    for entry in decisions:
        validate_decision_entry(entry)
        decision_id = entry["decision_id"]
        if decision_id in by_id:
            raise DecisionModelError(f"Duplicate decision_id: {decision_id}")
        by_id[decision_id] = entry

    known_decision_ids = known_decision_ids or set()
    for entry in decisions:
        supersedes = entry["supersedes"]
        if supersedes is None:
            continue
        if supersedes not in by_id and supersedes not in known_decision_ids:
            raise DecisionModelError(f"{entry['decision_id']} supersedes unknown decision_id {supersedes}")
        if supersedes == entry["decision_id"]:
            raise DecisionModelError(f"{entry['decision_id']} must not supersede itself")
        parent = by_id.get(supersedes)
        if parent is not None and parent["requirement_id"] != entry["requirement_id"]:
            raise DecisionModelError(f"{entry['decision_id']} supersedes a different requirement")
        if _revision(entry["decision_id"]) <= _revision(supersedes):
            raise DecisionModelError(f"{entry['decision_id']} revision must be greater than superseded revision")
    _validate_supersession_cycles(by_id)


def validate_decision_ledger(ledger: dict[str, Any]) -> None:
    if not isinstance(ledger, dict):
        raise DecisionModelError("Decision ledger must be an object")
    if ledger.get("schema_version") != SCHEMA_VERSION:
        raise DecisionModelError("Invalid decision ledger schema_version")
    if ledger.get("artifact_type") != DECISION_LEDGER_ARTIFACT_TYPE:
        raise DecisionModelError("Invalid decision ledger artifact_type")
    for key in SOURCE_DIGEST_KEYS:
        _digest(ledger.get("source_digests", {}).get(key), f"source_digests.{key}")
    records = ledger.get("records")
    if not isinstance(records, list):
        raise DecisionModelError("records must be a list")
    ids = []
    status_counts = Counter()
    authoritative = 0
    unresolved = 0
    follow_up = 0
    required_count = 0
    for record in records:
        if not isinstance(record, dict):
            raise DecisionModelError("Ledger records must be objects")
        requirement_id = _requirement_id(record.get("requirement_id"))
        ids.append(requirement_id)
        _digest(record.get("subject_digest"), f"{requirement_id}.subject_digest")
        status = _one_of(record.get("resolution_status"), LEDGER_STATUSES, f"{requirement_id}.resolution_status")
        status_counts[status] += 1
        if record.get("authoritative") is True:
            authoritative += 1
        if record.get("decision_required") is True:
            required_count += 1
            if status != "confirmed":
                unresolved += 1
        if record.get("follow_up_required") is True:
            follow_up += 1
    if ids != sorted(ids):
        raise DecisionModelError("Ledger records must be sorted by requirement_id")
    summary = ledger.get("summary")
    if not isinstance(summary, dict):
        raise DecisionModelError("summary must be an object")
    expected = {
        "total": len(records),
        "decision_required": required_count,
        "not_required": status_counts["not_required"],
        "pending": status_counts["pending"],
        "proposed": status_counts["proposed"],
        "confirmed": status_counts["confirmed"],
        "rejected": status_counts["rejected"],
        "stale": status_counts["stale"],
        "conflicting": status_counts["conflicting"],
        "authoritative": authoritative,
        "unresolved_required_count": unresolved,
        "follow_up_required_count": follow_up,
    }
    if summary != expected:
        raise DecisionModelError("Decision ledger summary does not match records")


def decision_revision(decision_id: str) -> int:
    return _revision(decision_id)


def decision_requirement_id(decision_id: str) -> str:
    return _requirement_id_from_decision_id(_decision_id(decision_id))


def _require_empty_selection_and_null_value(decision_id: str, selected: list[str], value: Any, action: str) -> None:
    if selected:
        raise DecisionModelError(f"{decision_id}: {action} must not select capabilities")
    if value is not None:
        raise DecisionModelError(f"{decision_id}: {action} must not include decision_value")


def _validate_supersession_cycles(by_id: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(decision_id: str, stack: list[str]) -> None:
        if decision_id in visited:
            return
        if decision_id in visiting:
            cycle = stack[stack.index(decision_id):] + [decision_id]
            raise DecisionModelError(f"Supersession cycle detected: {' -> '.join(cycle)}")
        visiting.add(decision_id)
        parent = by_id[decision_id].get("supersedes")
        if parent is not None and parent in by_id:
            visit(parent, stack + [parent])
        visiting.remove(decision_id)
        visited.add(decision_id)

    for decision_id in sorted(by_id):
        visit(decision_id, [decision_id])


def _revision(decision_id: str) -> int:
    return int(decision_id.rsplit(".r", 1)[1])


def _requirement_id_from_decision_id(decision_id: str) -> str:
    body = decision_id.removeprefix("dec.").rsplit(".r", 1)[0]
    return f"req.{body}"


def _decision_id(value: Any) -> str:
    if not isinstance(value, str) or not DECISION_ID_RE.match(value):
        raise DecisionModelError(f"Invalid decision_id: {value}")
    if _revision(value) < 1:
        raise DecisionModelError(f"Invalid decision revision: {value}")
    return value


def _requirement_id(value: Any) -> str:
    if not isinstance(value, str) or not REQUIREMENT_ID_RE.match(value):
        raise DecisionModelError(f"Invalid requirement_id: {value}")
    return value


def _digest(value: Any, context: str) -> str:
    if not isinstance(value, str) or not DIGEST_RE.match(value):
        raise DecisionModelError(f"{context} must be a sha256 digest")
    return value


def _require_fields(mapping: dict[str, Any], fields: list[str], context: str) -> None:
    missing = [field for field in fields if field not in mapping]
    if missing:
        raise DecisionModelError(f"{context} is missing fields: {', '.join(missing)}")


def _one_of(value: Any, allowed: set[str], context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionModelError(f"{context} must be a non-empty string")
    if value not in allowed:
        raise DecisionModelError(f"Invalid {context}: {value}")
    return value


def _string_list(value: Any, context: str) -> list[str]:
    if not isinstance(value, list):
        raise DecisionModelError(f"{context} must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise DecisionModelError(f"{context}[{index}] must be a non-empty string")
    return value


def _validate_unique(items: list[str], context: str) -> None:
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise DecisionModelError(f"{context} contains duplicate value(s): {', '.join(duplicates)}")


def _ensure_json_serializable(value: Any, context: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DecisionModelError(f"{context} must be JSON serializable: {exc}") from exc
