from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
from typing import Any
import hashlib
import re


SCHEMA_VERSION = "v0.12"
HANDOFF_MANIFEST_ARTIFACT_TYPE = "submission_handoff_manifest"
FREEZE_CONFIRMATION_ARTIFACT_TYPE = "freeze_confirmation_intake"
HANDOFF_SCOPE = "local_submission_candidate"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CHECK_ID_RE = re.compile(r"^handoff\.[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
FREEZE_CONFIRMATION_ID_RE = re.compile(r"^freeze\.local_submission_candidate\.r[0-9]{3}$")

CONFIRMATION_STATUSES = {"pending", "confirmed", "rejected"}
HANDOFF_STATUSES = {"blocked", "prepared", "frozen", "rejected", "stale", "conflicting"}
CHECK_STATUSES = {"pass", "fail", "warning"}
CHECK_SEVERITIES = {"blocker", "warning", "informational"}
PACKAGE_ROLES = {
    "submission",
    "validation_evidence",
    "human_approval",
    "decision_ledger",
    "requirements",
    "requirement_match",
    "capability_registry",
}


class HandoffModelError(ValueError):
    pass


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def sha256_file(path: str | Any) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def validate_package_path(path: str) -> None:
    if not isinstance(path, str) or not path:
        raise HandoffModelError("package_path must be a non-empty string")
    if "\x00" in path:
        raise HandoffModelError(f"Invalid package_path contains NUL: {path!r}")
    if "\\" in path:
        raise HandoffModelError(f"Invalid package_path contains backslash: {path}")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise HandoffModelError(f"Invalid absolute package_path: {path}")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise HandoffModelError(f"Invalid package_path segment: {path}")
    parsed = PurePosixPath(path)
    if parsed.as_posix() != path or parsed.is_absolute():
        raise HandoffModelError(f"Invalid package_path: {path}")


def validate_freeze_confirmation_entry(entry: dict[str, Any]) -> None:
    if not isinstance(entry, dict):
        raise HandoffModelError("Freeze confirmation entry must be an object")
    _require_fields(
        entry,
        [
            "confirmation_id",
            "scope",
            "expected_candidate_digest",
            "actor",
            "confirmation_status",
            "rationale",
            "supersedes",
            "notes",
        ],
        "freeze_confirmation",
    )
    confirmation_id = _confirmation_id(entry["confirmation_id"])
    if _revision(confirmation_id) < 1:
        raise HandoffModelError(f"{confirmation_id}: revision must be 001 or greater")
    if entry["scope"] != HANDOFF_SCOPE:
        raise HandoffModelError(f"{confirmation_id}: unsupported scope {entry['scope']}")
    _digest(entry["expected_candidate_digest"], f"{confirmation_id}.expected_candidate_digest")
    if entry["actor"] != "human":
        raise HandoffModelError(f"{confirmation_id}: actor must be human")
    status = _one_of(entry["confirmation_status"], CONFIRMATION_STATUSES, f"{confirmation_id}.confirmation_status")
    if not isinstance(entry["rationale"], str):
        raise HandoffModelError(f"{confirmation_id}.rationale must be a string")
    notes = _string_list(entry["notes"], f"{confirmation_id}.notes")
    _validate_unique(notes, f"{confirmation_id}.notes")
    supersedes = entry["supersedes"]
    if supersedes is not None:
        _confirmation_id(supersedes)
    if status in {"confirmed", "rejected"} and not entry["rationale"].strip():
        raise HandoffModelError(f"{confirmation_id}: {status} confirmation requires rationale")


def validate_freeze_confirmation_intake(
    intake: dict[str, Any],
    *,
    known_confirmation_ids: set[str] | None = None,
) -> None:
    if not isinstance(intake, dict):
        raise HandoffModelError("Freeze confirmation intake must be an object")
    if intake.get("schema_version") != SCHEMA_VERSION:
        raise HandoffModelError("Invalid freeze confirmation schema_version")
    if intake.get("artifact_type") != FREEZE_CONFIRMATION_ARTIFACT_TYPE:
        raise HandoffModelError("Invalid freeze confirmation artifact_type")
    if intake.get("scope") != HANDOFF_SCOPE:
        raise HandoffModelError("Invalid freeze confirmation scope")
    _digest(intake.get("candidate_digest"), "candidate_digest")
    confirmations = intake.get("confirmations")
    if not isinstance(confirmations, list):
        raise HandoffModelError("confirmations must be a list")
    notes = _string_list(intake.get("notes"), "notes")
    _validate_unique(notes, "notes")

    by_id: dict[str, dict[str, Any]] = {}
    for entry in confirmations:
        validate_freeze_confirmation_entry(entry)
        confirmation_id = entry["confirmation_id"]
        if confirmation_id in by_id:
            raise HandoffModelError(f"Duplicate confirmation_id: {confirmation_id}")
        by_id[confirmation_id] = entry

    known_confirmation_ids = known_confirmation_ids or set()
    for entry in confirmations:
        supersedes = entry["supersedes"]
        if supersedes is None:
            continue
        confirmation_id = entry["confirmation_id"]
        if supersedes not in by_id and supersedes not in known_confirmation_ids:
            raise HandoffModelError(f"{confirmation_id} supersedes unknown confirmation_id {supersedes}")
        if supersedes == confirmation_id:
            raise HandoffModelError(f"{confirmation_id} must not supersede itself")
        parent = by_id.get(supersedes)
        if parent is not None and parent["scope"] != entry["scope"]:
            raise HandoffModelError(f"{confirmation_id} supersedes a different scope")
        if _revision(confirmation_id) <= _revision(supersedes):
            raise HandoffModelError(f"{confirmation_id} revision must be greater than superseded revision")
    _validate_supersession_cycles(by_id)


def validate_handoff_manifest(manifest: dict[str, Any]) -> None:
    if not isinstance(manifest, dict):
        raise HandoffModelError("Handoff manifest must be an object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise HandoffModelError("Invalid handoff manifest schema_version")
    if manifest.get("artifact_type") != HANDOFF_MANIFEST_ARTIFACT_TYPE:
        raise HandoffModelError("Invalid handoff manifest artifact_type")
    if manifest.get("scope") != HANDOFF_SCOPE:
        raise HandoffModelError("Invalid handoff manifest scope")
    _one_of(manifest.get("status"), HANDOFF_STATUSES, "status")

    preflight = manifest.get("preflight")
    if not isinstance(preflight, dict):
        raise HandoffModelError("preflight must be an object")
    checks = preflight.get("checks")
    if not isinstance(checks, list):
        raise HandoffModelError("preflight.checks must be a list")
    blocker_count = 0
    warning_count = 0
    for check in checks:
        _validate_check(check)
        if check["severity"] == "blocker" and check["status"] == "fail":
            blocker_count += 1
        if check["severity"] == "warning" or check["status"] == "warning":
            warning_count += 1
    expected_status = "fail" if blocker_count else ("warning" if warning_count else "pass")
    if preflight.get("status") != expected_status:
        raise HandoffModelError("preflight.status does not match checks")
    if preflight.get("blocker_count") != blocker_count:
        raise HandoffModelError("preflight.blocker_count does not match checks")
    if preflight.get("warning_count") != warning_count:
        raise HandoffModelError("preflight.warning_count does not match checks")

    candidate = manifest.get("candidate")
    if not isinstance(candidate, dict):
        raise HandoffModelError("candidate must be an object")
    digest = candidate.get("candidate_digest")
    if digest is not None:
        _digest(digest, "candidate.candidate_digest")
    entries = candidate.get("entries")
    if not isinstance(entries, list):
        raise HandoffModelError("candidate.entries must be a list")
    if candidate.get("entry_count") != len(entries):
        raise HandoffModelError("candidate.entry_count does not match entries")
    if entries != sorted(entries, key=lambda item: item.get("package_path", "")):
        raise HandoffModelError("candidate.entries must be sorted by package_path")
    _validate_package_entries(entries)
    total_size = sum(entry["size_bytes"] for entry in entries)
    if candidate.get("total_size_bytes") != total_size:
        raise HandoffModelError("candidate.total_size_bytes does not match entries")


def freeze_confirmation_revision(confirmation_id: str) -> int:
    return _revision(_confirmation_id(confirmation_id))


def _validate_package_entries(entries: list[dict[str, Any]]) -> None:
    paths = []
    roles = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise HandoffModelError("Package entry must be an object")
        _require_fields(entry, ["package_path", "role", "media_type", "sha256", "size_bytes", "source_canonical_digest"], "package_entry")
        validate_package_path(entry["package_path"])
        paths.append(entry["package_path"])
        roles.append(entry["role"])
        _one_of(entry["role"], PACKAGE_ROLES, f"{entry['package_path']}.role")
        if not isinstance(entry["media_type"], str) or not entry["media_type"].strip():
            raise HandoffModelError(f"{entry['package_path']}.media_type must be a non-empty string")
        _digest(entry["sha256"], f"{entry['package_path']}.sha256")
        if not isinstance(entry["size_bytes"], int) or entry["size_bytes"] < 0:
            raise HandoffModelError(f"{entry['package_path']}.size_bytes must be a non-negative int")
        source_digest = entry["source_canonical_digest"]
        if source_digest is not None:
            _digest(source_digest, f"{entry['package_path']}.source_canonical_digest")
    for label, values in [("package_path", paths), ("role", roles)]:
        duplicates = sorted(item for item, count in Counter(values).items() if count > 1)
        if duplicates:
            raise HandoffModelError(f"Duplicate package {label}: {', '.join(duplicates)}")


def _validate_check(check: dict[str, Any]) -> None:
    if not isinstance(check, dict):
        raise HandoffModelError("Preflight check must be an object")
    _require_fields(check, ["check_id", "status", "severity", "observed", "expected", "notes"], "preflight_check")
    if not isinstance(check["check_id"], str) or not CHECK_ID_RE.match(check["check_id"]):
        raise HandoffModelError(f"Invalid preflight check_id: {check['check_id']}")
    _one_of(check["status"], CHECK_STATUSES, f"{check['check_id']}.status")
    _one_of(check["severity"], CHECK_SEVERITIES, f"{check['check_id']}.severity")
    notes = _string_list(check["notes"], f"{check['check_id']}.notes")
    _validate_unique(notes, f"{check['check_id']}.notes")


def _confirmation_id(value: Any) -> str:
    if not isinstance(value, str) or not FREEZE_CONFIRMATION_ID_RE.match(value):
        raise HandoffModelError(f"Invalid confirmation_id: {value}")
    return value


def _revision(identifier: str) -> int:
    return int(identifier.rsplit("r", 1)[1])


def _digest(value: Any, context: str) -> str:
    if not isinstance(value, str) or not DIGEST_RE.match(value):
        raise HandoffModelError(f"{context} must be a sha256 digest")
    return value


def _one_of(value: Any, allowed: set[str], context: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise HandoffModelError(f"{context} must be one of: {', '.join(sorted(allowed))}")
    return value


def _string_list(value: Any, context: str) -> list[str]:
    if not isinstance(value, list):
        raise HandoffModelError(f"{context} must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise HandoffModelError(f"{context}[{index}] must be a non-empty string")
    return value


def _validate_unique(items: list[str], context: str) -> None:
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise HandoffModelError(f"{context} contains duplicate value(s): {', '.join(duplicates)}")


def _require_fields(mapping: dict[str, Any], fields: list[str], context: str) -> None:
    missing = [field for field in fields if field not in mapping]
    if missing:
        raise HandoffModelError(f"{context} missing required field(s): {', '.join(missing)}")


def _validate_supersession_cycles(by_id: dict[str, dict[str, Any]]) -> None:
    for confirmation_id in sorted(by_id):
        seen: set[str] = set()
        current = confirmation_id
        while current in by_id and by_id[current]["supersedes"] is not None:
            if current in seen:
                raise HandoffModelError(f"Supersession cycle detected at {current}")
            seen.add(current)
            current = by_id[current]["supersedes"]
        if current in seen:
            raise HandoffModelError(f"Supersession cycle detected at {current}")
