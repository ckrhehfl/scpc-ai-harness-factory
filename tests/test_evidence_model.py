from __future__ import annotations

import re

import pytest

from factory.evidence_model import (
    EvidenceModelError,
    build_evidence_id,
    validate_evidence_index,
    validate_evidence_record,
)


def base_record_without_id() -> dict:
    return {
        "key": "file:train.csv:csv_structure",
        "status": "observed",
        "source_actor": "deterministic",
        "source_file": "train.csv",
        "source_type": "contest_package_file",
        "location": {"path": "train.csv", "scope": "table"},
        "extraction_method": "input_scanner.read_csv_preview",
        "observed_value": {
            "columns": ["id", "text", "label"],
            "column_count": 3,
            "row_count": 100,
            "first_row_preview": {"id": "1", "text": "example", "label": "positive"},
        },
        "confidence": "high",
    }


def with_id(record: dict) -> dict:
    return {"evidence_id": build_evidence_id(record), **record}


def test_evidence_id_is_stable_order_independent_and_content_sensitive():
    record = base_record_without_id()
    first = build_evidence_id(record)
    second = build_evidence_id(record)
    reordered = {
        "confidence": record["confidence"],
        "observed_value": {
            "row_count": 100,
            "first_row_preview": {"label": "positive", "text": "example", "id": "1"},
            "column_count": 3,
            "columns": ["id", "text", "label"],
        },
        "extraction_method": record["extraction_method"],
        "location": {"scope": "table", "path": "train.csv"},
        "source_type": record["source_type"],
        "source_file": record["source_file"],
        "source_actor": record["source_actor"],
        "status": record["status"],
        "key": record["key"],
    }
    changed = dict(record)
    changed["observed_value"] = dict(record["observed_value"], row_count=101)

    assert first == second
    assert first == build_evidence_id(reordered)
    assert first != build_evidence_id(changed)
    assert re.match(r"^ev_[0-9a-f]{16}$", first)


def test_evidence_id_ignores_artifact_and_output_metadata():
    record = base_record_without_id()
    with_metadata_a = dict(record, source_artifact="/tmp/a/input_scan_report.json", output_dir="generated")
    with_metadata_b = dict(record, source_artifact="/other/input_scan_report.json", output_dir="/tmp/out")

    assert build_evidence_id(with_metadata_a) == build_evidence_id(with_metadata_b)


def test_validate_evidence_record_accepts_valid_record():
    validate_evidence_record(with_id(base_record_without_id()))


@pytest.mark.parametrize("field", ["key", "status", "source_actor", "source_file", "observed_value"])
def test_validate_evidence_record_rejects_missing_required_fields(field):
    record = with_id(base_record_without_id())
    del record[field]

    with pytest.raises(EvidenceModelError):
        validate_evidence_record(record)


@pytest.mark.parametrize("source_file", ["/tmp/train.csv", "../train.csv", "data/../train.csv", "C:\\data\\train.csv"])
def test_validate_evidence_record_rejects_unsafe_source_paths(source_file):
    record = base_record_without_id()
    record["source_file"] = source_file
    record["location"] = {"path": source_file, "scope": "table"}
    record["key"] = f"file:{source_file}:csv_structure"
    record = with_id(record)

    with pytest.raises(EvidenceModelError):
        validate_evidence_record(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "inferred"),
        ("source_actor", "ai"),
        ("source_type", "local_file"),
        ("confidence", "medium"),
    ],
)
def test_validate_evidence_record_rejects_invalid_fixed_fields(field, value):
    record = base_record_without_id()
    record[field] = value
    record = with_id(record)

    with pytest.raises(EvidenceModelError):
        validate_evidence_record(record)


def test_validate_evidence_record_rejects_mismatched_id():
    record = with_id(base_record_without_id())
    record["observed_value"] = dict(record["observed_value"], row_count=999)

    with pytest.raises(EvidenceModelError):
        validate_evidence_record(record)


def test_validate_evidence_record_rejects_non_json_value():
    record = base_record_without_id()
    record["observed_value"] = {"bad": {1, 2, 3}}

    with pytest.raises(EvidenceModelError):
        build_evidence_id(record)


def test_validate_evidence_index_rejects_duplicate_ids():
    record = with_id(base_record_without_id())
    index = {
        "schema_version": "v0.9A",
        "artifact_type": "evidence_index",
        "contest_path": "examples/mock_contest_02",
        "source_artifact": "generated/input_scan_report.json",
        "record_count": 2,
        "records": [record, record],
    }

    with pytest.raises(EvidenceModelError):
        validate_evidence_index(index)
