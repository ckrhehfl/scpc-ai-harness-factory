from __future__ import annotations

import copy
import pytest

from factory.approval_model import (
    ApprovalModelError,
    build_readiness_digest,
    validate_approval_entry,
    validate_approval_intake,
    validate_gate_check,
)


DIGEST = "sha256:" + "0" * 64
SOURCES = {
    "contest_requirements": "sha256:" + "1" * 64,
    "requirement_capability_match": "sha256:" + "2" * 64,
    "decision_ledger": "sha256:" + "3" * 64,
    "capability_registry": "sha256:" + "4" * 64,
    "validation_report": None,
}


def approval(**overrides):
    entry = {
        "approval_id": "approval.local_submission_candidate.r001",
        "scope": "local_submission_candidate",
        "expected_readiness_digest": DIGEST,
        "actor": "human",
        "approval_status": "pending",
        "rationale": "",
        "conditions": [],
        "supersedes": None,
        "notes": [],
    }
    entry.update(overrides)
    return entry


def intake(*approvals):
    return {
        "schema_version": "v0.11B",
        "artifact_type": "human_approval_intake",
        "source_digests": dict(SOURCES),
        "readiness_digest": DIGEST,
        "approvals": list(approvals),
        "notes": [],
    }


def test_valid_approval_status_shapes():
    validate_approval_entry(approval())
    validate_approval_entry(approval(approval_status="approved", rationale="Approved."))
    validate_approval_entry(approval(approval_status="rejected", rationale="No-go."))
    validate_approval_entry(approval(approval_status="conditional", rationale="Conditional.", conditions=["Do x."]))


@pytest.mark.parametrize(
    "overrides",
    [
        {"approval_id": "bad"},
        {"approval_id": "approval.local_submission_candidate.r000"},
        {"scope": "official_submission"},
        {"actor": "ai"},
        {"expected_readiness_digest": "sha256:bad"},
        {"approval_status": "pending", "conditions": ["x"]},
        {"approval_status": "approved", "rationale": ""},
        {"approval_status": "approved", "rationale": "x", "conditions": ["x"]},
        {"approval_status": "rejected", "rationale": ""},
        {"approval_status": "conditional", "rationale": "x", "conditions": []},
    ],
)
def test_invalid_approval_entries_are_rejected(overrides):
    with pytest.raises(ApprovalModelError):
        validate_approval_entry(approval(**overrides))


def test_supersession_validation_duplicate_unknown_self_revision_and_cycle():
    with pytest.raises(ApprovalModelError):
        validate_approval_intake(intake(approval(), approval()))
    with pytest.raises(ApprovalModelError):
        validate_approval_intake(intake(approval(approval_id="approval.local_submission_candidate.r002", supersedes="approval.local_submission_candidate.r999")))
    with pytest.raises(ApprovalModelError):
        validate_approval_intake(intake(approval(supersedes="approval.local_submission_candidate.r001")))
    with pytest.raises(ApprovalModelError):
        validate_approval_intake(
            intake(
                approval(approval_id="approval.local_submission_candidate.r002"),
                approval(approval_id="approval.local_submission_candidate.r001", supersedes="approval.local_submission_candidate.r002"),
            )
        )
    cyclic = intake(
        approval(approval_id="approval.local_submission_candidate.r002", supersedes="approval.local_submission_candidate.r001"),
        approval(approval_id="approval.local_submission_candidate.r003", supersedes="approval.local_submission_candidate.r002"),
    )
    cyclic["approvals"][0]["supersedes"] = "approval.local_submission_candidate.r003"
    with pytest.raises(ApprovalModelError):
        validate_approval_intake(cyclic)


def test_gate_check_schema_validation():
    validate_gate_check(
        {
            "check_id": "gate.validation.present",
            "category": "validation",
            "status": "pass",
            "severity": "blocker",
            "observed": 0,
            "expected": 0,
            "related_requirement_ids": [],
            "related_capability_ids": [],
            "notes": [],
        }
    )
    with pytest.raises(ApprovalModelError):
        validate_gate_check(
            {
                "check_id": "bad",
                "category": "validation",
                "status": "pass",
                "severity": "blocker",
                "observed": 0,
                "expected": 0,
                "related_requirement_ids": [],
                "related_capability_ids": [],
                "notes": [],
            }
        )


def test_readiness_digest_is_deterministic_order_independent_and_changes_with_checks():
    machine = {"status": "reviewable", "blocker_count": 0, "warning_count": 0, "checks": []}
    reordered_sources = dict(reversed(list(SOURCES.items())))
    assert build_readiness_digest(SOURCES, machine) == build_readiness_digest(reordered_sources, copy.deepcopy(machine))
    changed = copy.deepcopy(machine)
    changed["checks"] = [{"check_id": "gate.validation.present", "status": "pass"}]
    assert build_readiness_digest(SOURCES, changed) != build_readiness_digest(SOURCES, machine)
