from __future__ import annotations

import copy

import pytest

from factory.requirement_model import (
    RequirementModelError,
    build_requirements_artifact,
    validate_requirement_record,
    validate_requirements_artifact,
)


def requirement(**overrides):
    data = {
        "requirement_id": "req.output.submission_csv_writing",
        "title": "Write submission CSV",
        "origin": "contest_spec",
        "domain": "output",
        "requirement_type": "capability",
        "priority": "must",
        "provenance_status": "observed",
        "applicability": "active",
        "risk_level": "green",
        "required_tokens": ["submission.csv.write"],
        "parameters": {"required_file": "submission.csv"},
        "source_refs": [{"artifact": "contest_spec.json", "path": "output.required_file"}],
        "evidence_ids": ["ev_0123456789abcdef"],
        "notes": ["local structural requirement"],
    }
    data.update(overrides)
    return data


def test_valid_requirement_is_allowed():
    validate_requirement_record(requirement())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("requirement_id", "bad"),
        ("origin", "bad"),
        ("domain", "bad"),
        ("requirement_type", "bad"),
        ("provenance_status", "bad"),
        ("applicability", "bad"),
        ("required_tokens", ["Submission.CSV.Write"]),
        ("evidence_ids", ["ev_nothex"]),
    ],
)
def test_invalid_fields_are_rejected(field, value):
    with pytest.raises(RequirementModelError):
        validate_requirement_record(requirement(**{field: value}))


def test_capability_requires_tokens_but_non_capability_allows_empty_tokens():
    with pytest.raises(RequirementModelError):
        validate_requirement_record(requirement(required_tokens=[]))
    validate_requirement_record(requirement(requirement_type="constraint", required_tokens=[]))


def test_duplicate_tokens_and_bad_source_ref_are_rejected():
    with pytest.raises(RequirementModelError):
        validate_requirement_record(requirement(required_tokens=["a.b", "a.b"]))
    with pytest.raises(RequirementModelError):
        validate_requirement_record(requirement(source_refs=[{"artifact": "bad", "path": "x"}]))


def test_duplicate_requirement_id_rejected_and_summary_checked():
    req = requirement()
    with pytest.raises(RequirementModelError):
        build_requirements_artifact(
            [req, copy.deepcopy(req)],
            source_artifacts={"contest_spec": "generated/contest_spec.json", "evidence_index": "generated/evidence_index.json", "coverage": None},
        )


def test_artifact_is_sorted_and_deterministic():
    second = requirement(
        requirement_id="req.runtime.test_csv_loading",
        domain="runtime",
        required_tokens=["harness.test_csv.load"],
    )
    artifact_a = build_requirements_artifact(
        [requirement(), second],
        source_artifacts={"contest_spec": "generated/contest_spec.json", "evidence_index": "generated/evidence_index.json", "coverage": None},
    )
    artifact_b = build_requirements_artifact(
        [requirement(), second],
        source_artifacts={"contest_spec": "generated/contest_spec.json", "evidence_index": "generated/evidence_index.json", "coverage": None},
    )
    assert [item["requirement_id"] for item in artifact_a["requirements"]] == [
        "req.output.submission_csv_writing",
        "req.runtime.test_csv_loading",
    ]
    assert artifact_a == artifact_b
    validate_requirements_artifact(artifact_a)
    broken = copy.deepcopy(artifact_a)
    broken["summary"]["total"] = 99
    with pytest.raises(RequirementModelError):
        validate_requirements_artifact(broken)
