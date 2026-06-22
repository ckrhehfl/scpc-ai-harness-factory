from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
import re


SCHEMA_VERSION = "v0.13"
SCOPE = "local_submission_candidate"
RECEIPT_INTAKE_ARTIFACT_TYPE = "submission_receipt_intake"
EVIDENCE_INDEX_ARTIFACT_TYPE = "submission_receipt_evidence_index"
POST_SUBMISSION_AUDIT_ARTIFACT_TYPE = "post_submission_audit"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RECEIPT_ID_RE = re.compile(r"^receipt\.local_submission_candidate\.r[0-9]{3}$")
EVIDENCE_ID_RE = re.compile(r"^receipt_ev\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
PLATFORM_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
CHECK_ID_RE = re.compile(r"^audit\.[a-z0-9_]+(?:\.[a-z0-9_]+)+$")

RECEIPT_STATUSES = {"pending", "recorded", "retracted"}
PLATFORM_STATUSES = {"unknown", "submitted", "processing", "accepted", "scored", "rejected", "failed", "cancelled"}
SCORE_SCOPES = {"public", "private", "provisional", "final", "unknown"}
MEDIA_TYPES = {"image/png", "image/jpeg", "application/pdf", "text/plain", "application/json"}
RECEIPT_STATE_STATUSES = {"not_provided", "pending", "recorded", "retracted", "stale", "conflicting"}
AUDIT_STATUSES = {"blocked", "awaiting_receipt", "pending", "complete", "retracted", "stale", "conflicting"}
ARTIFACT_BINDING_STATUSES = {"blocked", "matched"}
CHECK_STATUSES = {"pass", "fail", "warning"}
CHECK_SEVERITIES = {"blocker", "warning", "informational"}


class ReceiptModelError(ValueError):
    pass


def validate_receipt_evidence_declaration(item: dict[str, Any]) -> None:
    if not isinstance(item, dict):
        raise ReceiptModelError("Evidence declaration must be an object")
    _require_fields(item, ["evidence_id", "relative_path", "media_type", "description"], "evidence_file")
    _evidence_id(item["evidence_id"])
    _relative_path(item["relative_path"], f"{item['evidence_id']}.relative_path")
    _one_of(item["media_type"], MEDIA_TYPES, f"{item['evidence_id']}.media_type")
    if not isinstance(item["description"], str) or not item["description"].strip():
        raise ReceiptModelError(f"{item['evidence_id']}.description must be a non-empty string")


def validate_submission_receipt_entry(entry: dict[str, Any]) -> None:
    if not isinstance(entry, dict):
        raise ReceiptModelError("Receipt entry must be an object")
    _require_fields(
        entry,
        [
            "receipt_id",
            "scope",
            "expected_candidate_digest",
            "expected_submission_sha256",
            "actor",
            "receipt_status",
            "platform",
            "submission_identifier",
            "submitted_at",
            "uploaded_filename",
            "platform_status",
            "score",
            "evidence_ids",
            "rationale",
            "supersedes",
            "notes",
        ],
        "receipt",
    )
    receipt_id = _receipt_id(entry["receipt_id"])
    if _revision(receipt_id) < 1:
        raise ReceiptModelError(f"{receipt_id}: revision must be 001 or greater")
    if entry["scope"] != SCOPE:
        raise ReceiptModelError(f"{receipt_id}: unsupported scope {entry['scope']}")
    _digest(entry["expected_candidate_digest"], f"{receipt_id}.expected_candidate_digest")
    _digest(entry["expected_submission_sha256"], f"{receipt_id}.expected_submission_sha256")
    if entry["actor"] != "human":
        raise ReceiptModelError(f"{receipt_id}: actor must be human")
    status = _one_of(entry["receipt_status"], RECEIPT_STATUSES, f"{receipt_id}.receipt_status")
    platform_status = _one_of(entry["platform_status"], PLATFORM_STATUSES, f"{receipt_id}.platform_status")
    evidence_ids = _string_list(entry["evidence_ids"], f"{receipt_id}.evidence_ids")
    _validate_unique(evidence_ids, f"{receipt_id}.evidence_ids")
    for evidence_id in evidence_ids:
        _evidence_id(evidence_id)
    if not isinstance(entry["rationale"], str):
        raise ReceiptModelError(f"{receipt_id}.rationale must be a string")
    notes = _string_list(entry["notes"], f"{receipt_id}.notes")
    _validate_unique(notes, f"{receipt_id}.notes")
    if entry["supersedes"] is not None:
        _receipt_id(entry["supersedes"])
    _validate_score_shape(receipt_id, platform_status, entry["score"])

    if status == "pending":
        expected = {
            "platform": None,
            "submission_identifier": None,
            "submitted_at": None,
            "uploaded_filename": None,
            "platform_status": "unknown",
            "score": None,
            "evidence_ids": [],
        }
        for key, value in expected.items():
            if entry[key] != value:
                raise ReceiptModelError(f"{receipt_id}: pending receipt requires {key}={value!r}")
        return

    if status == "recorded":
        _platform(entry["platform"], f"{receipt_id}.platform")
        _non_empty_string(entry["submission_identifier"], f"{receipt_id}.submission_identifier")
        _timestamp_with_timezone(entry["submitted_at"], f"{receipt_id}.submitted_at")
        _basename(entry["uploaded_filename"], f"{receipt_id}.uploaded_filename")
        if not entry["rationale"].strip():
            raise ReceiptModelError(f"{receipt_id}: recorded receipt requires rationale")
        return

    if status == "retracted":
        if entry["supersedes"] is None:
            raise ReceiptModelError(f"{receipt_id}: retracted receipt requires supersedes")
        if not entry["rationale"].strip():
            raise ReceiptModelError(f"{receipt_id}: retracted receipt requires rationale")
        for key in ["platform", "submission_identifier", "submitted_at", "uploaded_filename", "score"]:
            if entry[key] is not None:
                raise ReceiptModelError(f"{receipt_id}: retracted receipt requires {key}=None")
        if entry["platform_status"] != "unknown":
            raise ReceiptModelError(f"{receipt_id}: retracted receipt requires platform_status=unknown")
        if entry["evidence_ids"] != []:
            raise ReceiptModelError(f"{receipt_id}: retracted receipt requires evidence_ids=[]")


def validate_submission_receipt_intake(
    intake: dict[str, Any],
    *,
    known_receipt_ids: set[str] | None = None,
) -> None:
    if not isinstance(intake, dict):
        raise ReceiptModelError("Submission receipt intake must be an object")
    if intake.get("schema_version") != SCHEMA_VERSION:
        raise ReceiptModelError("Invalid receipt intake schema_version")
    if intake.get("artifact_type") != RECEIPT_INTAKE_ARTIFACT_TYPE:
        raise ReceiptModelError("Invalid receipt intake artifact_type")
    if intake.get("scope") != SCOPE:
        raise ReceiptModelError("Invalid receipt intake scope")
    source_digests = intake.get("source_digests")
    if not isinstance(source_digests, dict):
        raise ReceiptModelError("source_digests must be an object")
    _digest(source_digests.get("handoff_manifest"), "source_digests.handoff_manifest")
    _digest(source_digests.get("handoff_archive"), "source_digests.handoff_archive")
    _digest(intake.get("candidate_digest"), "candidate_digest")
    _digest(intake.get("submission_sha256"), "submission_sha256")
    evidence_files = intake.get("evidence_files")
    receipts = intake.get("receipts")
    if not isinstance(evidence_files, list):
        raise ReceiptModelError("evidence_files must be a list")
    if not isinstance(receipts, list):
        raise ReceiptModelError("receipts must be a list")
    notes = _string_list(intake.get("notes"), "notes")
    _validate_unique(notes, "notes")

    evidence_ids = []
    for item in evidence_files:
        validate_receipt_evidence_declaration(item)
        evidence_ids.append(item["evidence_id"])
    _validate_unique(evidence_ids, "evidence_files.evidence_id")
    known_evidence_ids = set(evidence_ids)

    by_id: dict[str, dict[str, Any]] = {}
    for entry in receipts:
        validate_submission_receipt_entry(entry)
        receipt_id = entry["receipt_id"]
        if receipt_id in by_id:
            raise ReceiptModelError(f"Duplicate receipt_id: {receipt_id}")
        unknown_evidence = sorted(set(entry["evidence_ids"]) - known_evidence_ids)
        if unknown_evidence:
            raise ReceiptModelError(f"{receipt_id}: unknown evidence_id(s): {', '.join(unknown_evidence)}")
        by_id[receipt_id] = entry

    known_receipt_ids = known_receipt_ids or set()
    for entry in receipts:
        supersedes = entry["supersedes"]
        if supersedes is None:
            continue
        receipt_id = entry["receipt_id"]
        if supersedes not in by_id and supersedes not in known_receipt_ids:
            raise ReceiptModelError(f"{receipt_id} supersedes unknown receipt_id {supersedes}")
        if supersedes == receipt_id:
            raise ReceiptModelError(f"{receipt_id} must not supersede itself")
        parent = by_id.get(supersedes)
        if parent is not None and parent["scope"] != entry["scope"]:
            raise ReceiptModelError(f"{receipt_id} supersedes a different scope")
        if _revision(receipt_id) <= _revision(supersedes):
            raise ReceiptModelError(f"{receipt_id} revision must be greater than superseded revision")
    _validate_supersession_cycles(by_id)


def validate_receipt_evidence_index(index: dict[str, Any]) -> None:
    if not isinstance(index, dict):
        raise ReceiptModelError("Evidence index must be an object")
    if index.get("schema_version") != SCHEMA_VERSION:
        raise ReceiptModelError("Invalid evidence index schema_version")
    if index.get("artifact_type") != EVIDENCE_INDEX_ARTIFACT_TYPE:
        raise ReceiptModelError("Invalid evidence index artifact_type")
    if index.get("scope") != SCOPE:
        raise ReceiptModelError("Invalid evidence index scope")
    items = index.get("items")
    if not isinstance(items, list):
        raise ReceiptModelError("items must be a list")
    ids = []
    for item in items:
        if not isinstance(item, dict):
            raise ReceiptModelError("Evidence index item must be an object")
        _require_fields(item, ["evidence_id", "filename", "media_type", "description", "sha256", "size_bytes"], "evidence_index.item")
        ids.append(_evidence_id(item["evidence_id"]))
        _basename(item["filename"], f"{item['evidence_id']}.filename")
        _one_of(item["media_type"], MEDIA_TYPES, f"{item['evidence_id']}.media_type")
        if not isinstance(item["description"], str) or not item["description"].strip():
            raise ReceiptModelError(f"{item['evidence_id']}.description must be a non-empty string")
        _digest(item["sha256"], f"{item['evidence_id']}.sha256")
        if not isinstance(item["size_bytes"], int) or item["size_bytes"] <= 0:
            raise ReceiptModelError(f"{item['evidence_id']}.size_bytes must be a positive int")
    if items != sorted(items, key=lambda item: item["evidence_id"]):
        raise ReceiptModelError("Evidence index items must be sorted by evidence_id")
    _validate_unique(ids, "evidence_index.items.evidence_id")
    warnings = _string_list(index.get("warnings"), "warnings")
    _validate_unique(warnings, "warnings")


def validate_post_submission_audit(audit: dict[str, Any]) -> None:
    if not isinstance(audit, dict):
        raise ReceiptModelError("Post-submission audit must be an object")
    if audit.get("schema_version") != SCHEMA_VERSION:
        raise ReceiptModelError("Invalid post-submission audit schema_version")
    if audit.get("artifact_type") != POST_SUBMISSION_AUDIT_ARTIFACT_TYPE:
        raise ReceiptModelError("Invalid post-submission audit artifact_type")
    if audit.get("scope") != SCOPE:
        raise ReceiptModelError("Invalid post-submission audit scope")
    _one_of(audit.get("status"), AUDIT_STATUSES, "status")
    binding = audit.get("handoff_binding")
    if not isinstance(binding, dict):
        raise ReceiptModelError("handoff_binding must be an object")
    _one_of(binding.get("status"), ARTIFACT_BINDING_STATUSES, "handoff_binding.status")
    state = audit.get("receipt_state")
    if not isinstance(state, dict):
        raise ReceiptModelError("receipt_state must be an object")
    _one_of(state.get("status"), RECEIPT_STATE_STATUSES, "receipt_state.status")
    if not isinstance(state.get("authoritative"), bool):
        raise ReceiptModelError("receipt_state.authoritative must be a bool")
    checks = audit.get("checks")
    if not isinstance(checks, list):
        raise ReceiptModelError("checks must be a list")
    for check in checks:
        _validate_check(check)
    history = state.get("history")
    if not isinstance(history, list):
        raise ReceiptModelError("receipt_state.history must be a list")
    if history != sorted(history, key=lambda item: (_revision(item["receipt_id"]), item["receipt_id"])):
        raise ReceiptModelError("receipt_state.history must be sorted by revision and receipt_id")


def receipt_revision(receipt_id: str) -> int:
    return _revision(_receipt_id(receipt_id))


def _validate_score_shape(receipt_id: str, platform_status: str, score: Any) -> None:
    if platform_status == "scored":
        if not isinstance(score, dict):
            raise ReceiptModelError(f"{receipt_id}: scored platform_status requires score")
    elif score is not None:
        raise ReceiptModelError(f"{receipt_id}: score must be null unless platform_status is scored")
    if score is None:
        return
    _require_fields(score, ["value", "metric", "scope"], f"{receipt_id}.score")
    _non_empty_string(score["value"], f"{receipt_id}.score.value")
    if score["metric"] is not None:
        _non_empty_string(score["metric"], f"{receipt_id}.score.metric")
    _one_of(score["scope"], SCORE_SCOPES, f"{receipt_id}.score.scope")


def _validate_check(check: dict[str, Any]) -> None:
    if not isinstance(check, dict):
        raise ReceiptModelError("Audit check must be an object")
    _require_fields(check, ["check_id", "category", "status", "severity", "observed", "expected", "notes"], "audit_check")
    if not isinstance(check["check_id"], str) or not CHECK_ID_RE.match(check["check_id"]):
        raise ReceiptModelError(f"Invalid audit check_id: {check['check_id']}")
    _one_of(check["status"], CHECK_STATUSES, f"{check['check_id']}.status")
    _one_of(check["severity"], CHECK_SEVERITIES, f"{check['check_id']}.severity")
    notes = _string_list(check["notes"], f"{check['check_id']}.notes")
    _validate_unique(notes, f"{check['check_id']}.notes")


def _receipt_id(value: Any) -> str:
    if not isinstance(value, str) or not RECEIPT_ID_RE.match(value):
        raise ReceiptModelError(f"Invalid receipt_id: {value}")
    return value


def _evidence_id(value: Any) -> str:
    if not isinstance(value, str) or not EVIDENCE_ID_RE.match(value):
        raise ReceiptModelError(f"Invalid evidence_id: {value}")
    return value


def _platform(value: Any, context: str) -> str:
    if not isinstance(value, str) or not PLATFORM_RE.match(value):
        raise ReceiptModelError(f"{context} must be a platform token")
    return value


def _digest(value: Any, context: str) -> str:
    if not isinstance(value, str) or not DIGEST_RE.match(value):
        raise ReceiptModelError(f"{context} must be a sha256 digest")
    return value


def _one_of(value: Any, allowed: set[str], context: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ReceiptModelError(f"{context} must be one of: {', '.join(sorted(allowed))}")
    return value


def _non_empty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReceiptModelError(f"{context} must be a non-empty string")
    return value


def _string_list(value: Any, context: str) -> list[str]:
    if not isinstance(value, list):
        raise ReceiptModelError(f"{context} must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ReceiptModelError(f"{context}[{index}] must be a non-empty string")
    return value


def _basename(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReceiptModelError(f"{context} must be a basename")
    if "/" in value or "\\" in value or value in {".", ".."} or "\x00" in value:
        raise ReceiptModelError(f"{context} must be a basename")
    if PurePosixPath(value).name != value:
        raise ReceiptModelError(f"{context} must be a basename")
    return value


def _timestamp_with_timezone(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReceiptModelError(f"{context} must be an RFC3339 timestamp with timezone")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReceiptModelError(f"{context} must be an RFC3339 timestamp with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReceiptModelError(f"{context} must include a timezone offset")
    if " " in value:
        raise ReceiptModelError(f"{context} must use ISO-8601 T separator")
    return value


def _relative_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReceiptModelError(f"{context} must be a non-empty POSIX relative path")
    if "\x00" in value or "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ReceiptModelError(f"{context} must be a safe POSIX relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ReceiptModelError(f"{context} must not contain empty, '.', or '..' segments")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or parsed.as_posix() != value:
        raise ReceiptModelError(f"{context} must be a safe POSIX relative path")
    return value


def _revision(identifier: str) -> int:
    return int(identifier.rsplit("r", 1)[1])


def _validate_unique(items: list[str], context: str) -> None:
    duplicates = sorted(item for item, count in Counter(items).items() if count > 1)
    if duplicates:
        raise ReceiptModelError(f"{context} contains duplicate value(s): {', '.join(duplicates)}")


def _require_fields(mapping: dict[str, Any], fields: list[str], context: str) -> None:
    missing = [field for field in fields if field not in mapping]
    if missing:
        raise ReceiptModelError(f"{context} missing required field(s): {', '.join(missing)}")


def _validate_supersession_cycles(by_id: dict[str, dict[str, Any]]) -> None:
    for receipt_id in sorted(by_id):
        seen: set[str] = set()
        current = receipt_id
        while current in by_id and by_id[current]["supersedes"] is not None:
            if current in seen:
                raise ReceiptModelError(f"Supersession cycle detected at {current}")
            seen.add(current)
            current = by_id[current]["supersedes"]
        if current in seen:
            raise ReceiptModelError(f"Supersession cycle detected at {current}")
