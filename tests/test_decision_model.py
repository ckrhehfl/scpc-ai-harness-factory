from __future__ import annotations

import copy
import pytest

from factory.decision_model import (
    DecisionModelError,
    build_subject_digest,
    canonical_json_digest,
    validate_decision_entry,
    validate_decision_intake,
)


DIGEST = "sha256:" + "0" * 64
SOURCE_DIGESTS = {
    "contest_requirements": "sha256:" + "1" * 64,
    "requirement_capability_match": "sha256:" + "2" * 64,
    "capability_registry": "sha256:" + "3" * 64,
}


def decision(**overrides):
    entry = {
        "decision_id": "dec.solver.task_solution.r001",
        "requirement_id": "req.solver.task_solution",
        "expected_subject_digest": DIGEST,
        "actor": "human",
        "decision_status": "pending",
        "action": "no_action",
        "decision_value": None,
        "rationale": "",
        "selected_capability_ids": [],
        "evidence_ids": [],
        "conditions": [],
        "supersedes": None,
        "notes": [],
    }
    entry.update(overrides)
    return entry


def intake(*decisions):
    return {
        "schema_version": "v0.11A",
        "artifact_type": "decision_intake",
        "source_digests": dict(SOURCE_DIGESTS),
        "decisions": list(decisions),
        "notes": [],
    }


def test_canonical_digest_is_deterministic_and_key_order_independent():
    left = {"b": [2, 1], "a": {"x": "한글"}}
    right = {"a": {"x": "한글"}, "b": [2, 1]}
    assert canonical_json_digest(left) == canonical_json_digest(left)
    assert canonical_json_digest(left) == canonical_json_digest(right)
    assert canonical_json_digest(left).startswith("sha256:")


def test_subject_digest_changes_when_requirement_or_match_changes():
    requirement = {"requirement_id": "req.a.b", "value": 1}
    match = {"requirement_id": "req.a.b", "match_status": "unmet"}
    baseline = build_subject_digest(requirement, match)
    changed_requirement = copy.deepcopy(requirement)
    changed_requirement["value"] = 2
    changed_match = copy.deepcopy(match)
    changed_match["match_status"] = "satisfied"
    assert build_subject_digest(changed_requirement, match) != baseline
    assert build_subject_digest(requirement, changed_match) != baseline


def test_pending_template_entry_is_valid():
    validate_decision_entry(decision())
    validate_decision_intake(intake(decision()))


@pytest.mark.parametrize(
    "overrides",
    [
        {"decision_id": "bad"},
        {"decision_id": "dec.solver.other.r001"},
        {"actor": "ai", "decision_status": "confirmed", "action": "implement_missing_capability", "rationale": "x"},
        {"actor": "ai", "decision_status": "pending"},
        {"actor": "human", "decision_status": "proposed", "action": "implement_missing_capability", "rationale": "x"},
        {"decision_status": "confirmed", "action": "no_action", "rationale": "x"},
        {"decision_status": "pending", "action": "wait_for_information"},
        {"decision_status": "confirmed", "action": "wait_for_information", "rationale": ""},
        {"decision_status": "confirmed", "action": "confirm_value", "rationale": "x", "decision_value": None},
        {"decision_status": "confirmed", "action": "confirm_value", "rationale": "x", "decision_value": "unknown"},
        {"decision_status": "confirmed", "action": "wait_for_information", "rationale": "x", "decision_value": "x"},
        {"decision_status": "confirmed", "action": "use_existing_capability", "rationale": "x"},
        {"evidence_ids": ["bad"]},
        {"conditions": [""]},
        {"notes": [""]},
    ],
)
def test_invalid_decision_entries_are_rejected(overrides):
    with pytest.raises(DecisionModelError):
        validate_decision_entry(decision(**overrides))


def test_duplicate_decision_id_is_rejected():
    with pytest.raises(DecisionModelError):
        validate_decision_intake(intake(decision(), decision()))


def test_invalid_source_digest_is_rejected():
    data = intake(decision())
    data["source_digests"]["contest_requirements"] = "sha256:bad"
    with pytest.raises(DecisionModelError):
        validate_decision_intake(data)


def test_supersession_root_and_next_revision_are_valid():
    first = decision(actor="ai", decision_status="proposed", action="implement_missing_capability", rationale="Needs solver.")
    second = decision(
        decision_id="dec.solver.task_solution.r002",
        decision_status="confirmed",
        action="implement_missing_capability",
        rationale="Implement solver.",
        supersedes=first["decision_id"],
    )
    validate_decision_intake(intake(first, second))


@pytest.mark.parametrize(
    "second_overrides",
    [
        {"supersedes": "dec.solver.task_solution.r999"},
        {"supersedes": "dec.other.task.r001"},
        {"decision_id": "dec.solver.task_solution.r001", "supersedes": "dec.solver.task_solution.r001"},
        {"decision_id": "dec.solver.task_solution.r001", "supersedes": "dec.solver.task_solution.r001"},
    ],
)
def test_invalid_supersession_rejected(second_overrides):
    first = decision()
    second = decision(
        decision_id="dec.solver.task_solution.r002",
        decision_status="confirmed",
        action="wait_for_information",
        rationale="Wait.",
        supersedes=first["decision_id"],
    )
    second.update(second_overrides)
    with pytest.raises(DecisionModelError):
        validate_decision_intake(intake(first, second))


def test_lower_or_equal_revision_supersession_is_rejected():
    first = decision(decision_id="dec.solver.task_solution.r002")
    second = decision(
        decision_id="dec.solver.task_solution.r001",
        decision_status="confirmed",
        action="wait_for_information",
        rationale="Wait.",
        supersedes=first["decision_id"],
    )
    with pytest.raises(DecisionModelError):
        validate_decision_intake(intake(first, second))
