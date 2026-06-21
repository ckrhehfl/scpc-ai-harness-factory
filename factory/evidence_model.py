from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any
import hashlib
import json
import re


SCHEMA_VERSION = "v0.9A"
ARTIFACT_TYPE = "evidence_index"
STATUS_OBSERVED = "observed"
SOURCE_ACTOR_DETERMINISTIC = "deterministic"
SOURCE_TYPE_CONTEST_FILE = "contest_package_file"
CONFIDENCE_HIGH = "high"

EVIDENCE_ID_RE = re.compile(r"^ev_[0-9a-f]{16}$")
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")

EVIDENCE_ID_FIELDS = [
    "key",
    "status",
    "source_actor",
    "source_file",
    "source_type",
    "location",
    "extraction_method",
    "observed_value",
    "confidence",
]

REQUIRED_RECORD_FIELDS = ["evidence_id", *EVIDENCE_ID_FIELDS]


class EvidenceModelError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceModelError(f"Value is not JSON serializable: {exc}") from exc


def normalize_source_path(path: Any) -> str:
    if not isinstance(path, str):
        raise EvidenceModelError("source_file path must be a string")
    normalized = path.replace("\\", "/")
    if not normalized:
        raise EvidenceModelError("source_file path must not be empty")
    if normalized.startswith("/") or WINDOWS_DRIVE_RE.match(normalized):
        raise EvidenceModelError(f"source_file path must be relative: {path}")
    pure_path = PurePosixPath(normalized)
    parts = pure_path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise EvidenceModelError(f"source_file path is not safe: {path}")
    if pure_path.as_posix() != normalized:
        raise EvidenceModelError(f"source_file path is not normalized: {path}")
    return normalized


def build_evidence_id(record_without_id: dict[str, Any]) -> str:
    missing = [field for field in EVIDENCE_ID_FIELDS if field not in record_without_id]
    if missing:
        raise EvidenceModelError(f"Evidence ID source is missing fields: {', '.join(missing)}")
    payload = {field: record_without_id[field] for field in EVIDENCE_ID_FIELDS}
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"ev_{digest[:16]}"


def validate_evidence_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        raise EvidenceModelError("Evidence record must be an object")

    missing = [field for field in REQUIRED_RECORD_FIELDS if field not in record]
    if missing:
        raise EvidenceModelError(f"Evidence record is missing fields: {', '.join(missing)}")

    evidence_id = record["evidence_id"]
    if not isinstance(evidence_id, str) or not EVIDENCE_ID_RE.match(evidence_id):
        raise EvidenceModelError(f"Invalid evidence_id: {evidence_id}")

    source_file = normalize_source_path(record["source_file"])
    key = record["key"]
    if not isinstance(key, str) or not key.startswith("file:"):
        raise EvidenceModelError("Evidence key must start with file:")
    expected_key_prefix = f"file:{source_file}:"
    if not key.startswith(expected_key_prefix) or key == expected_key_prefix:
        raise EvidenceModelError(f"Evidence key must match source_file: {key}")

    if record["status"] != STATUS_OBSERVED:
        raise EvidenceModelError(f"Invalid status: {record['status']}")
    if record["source_actor"] != SOURCE_ACTOR_DETERMINISTIC:
        raise EvidenceModelError(f"Invalid source_actor: {record['source_actor']}")
    if record["source_type"] != SOURCE_TYPE_CONTEST_FILE:
        raise EvidenceModelError(f"Invalid source_type: {record['source_type']}")
    if record["confidence"] != CONFIDENCE_HIGH:
        raise EvidenceModelError(f"Invalid confidence: {record['confidence']}")

    location = record["location"]
    if not isinstance(location, dict):
        raise EvidenceModelError("location must be an object")
    if normalize_source_path(location.get("path")) != source_file:
        raise EvidenceModelError("location.path must match source_file")
    scope = location.get("scope")
    if not isinstance(scope, str) or not scope:
        raise EvidenceModelError("location.scope must be a non-empty string")

    extraction_method = record["extraction_method"]
    if not isinstance(extraction_method, str) or not extraction_method:
        raise EvidenceModelError("extraction_method must be a non-empty string")

    canonical_json(record["observed_value"])

    expected_id = build_evidence_id({field: record[field] for field in EVIDENCE_ID_FIELDS})
    if evidence_id != expected_id:
        raise EvidenceModelError("evidence_id does not match record content")


def validate_evidence_index(index: dict[str, Any]) -> None:
    if not isinstance(index, dict):
        raise EvidenceModelError("Evidence index must be an object")
    if index.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceModelError(f"Invalid schema_version: {index.get('schema_version')}")
    if index.get("artifact_type") != ARTIFACT_TYPE:
        raise EvidenceModelError(f"Invalid artifact_type: {index.get('artifact_type')}")

    records = index.get("records")
    if not isinstance(records, list):
        raise EvidenceModelError("records must be a list")
    if index.get("record_count") != len(records):
        raise EvidenceModelError("record_count must match len(records)")

    seen_ids: set[str] = set()
    for record in records:
        validate_evidence_record(record)
        evidence_id = record["evidence_id"]
        if evidence_id in seen_ids:
            raise EvidenceModelError(f"Duplicate evidence_id: {evidence_id}")
        seen_ids.add(evidence_id)

    sorted_records = sorted(records, key=lambda item: (item["source_file"], item["key"], item["evidence_id"]))
    if records != sorted_records:
        raise EvidenceModelError("records must be sorted by source_file, key, evidence_id")
