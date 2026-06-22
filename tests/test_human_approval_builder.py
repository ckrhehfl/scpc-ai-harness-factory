from __future__ import annotations

import copy
import json

import pytest

from factory.decision_ledger_builder import build_decision_ledger
from factory.decision_model import build_subject_digest, canonical_json_digest
from factory.human_approval_builder import (
    build_human_approval_intake_template,
    build_human_approval_summary,
    render_human_approval_summary_markdown,
)
from factory.requirement_model import build_match_summary, build_requirements_artifact


def req(requirement_id="req.solver.task_solution", *, priority="must", applicability="active", risk_level="red"):
    return {
        "requirement_id": requirement_id,
        "title": requirement_id,
        "origin": "contest_spec",
        "domain": "solver",
        "requirement_type": "capability",
        "priority": priority,
        "provenance_status": "observed",
        "applicability": applicability,
        "risk_level": risk_level,
        "required_tokens": ["solver.classification.predict"],
        "parameters": {},
        "source_refs": [{"artifact": "contest_spec.json", "path": "problem"}],
        "evidence_ids": [],
        "notes": [],
    }


def match(requirement_id="req.solver.task_solution", *, status="satisfied", matched=None, dependencies=None):
    matched = ["cap.solver.classification"] if matched is None and status == "satisfied" else (matched or [])
    return {
        "requirement_id": requirement_id,
        "match_status": status,
        "required_tokens": ["solver.classification.predict"],
        "token_matches": [
            {
                "token": "solver.classification.predict",
                "eligible_capability_ids": matched,
                "limited_capability_ids": [],
                "ineligible_capability_ids": [],
                "blocked_capability_ids": [],
            }
        ],
        "matched_capability_ids": matched,
        "dependency_capability_ids": dependencies or [],
        "missing_tokens": [] if status == "satisfied" else ["solver.classification.predict"],
        "blocked_by": [],
        "notes": [],
    }


def cap(capability_id="cap.solver.classification", *, verification="verified", eligibility="eligible"):
    return {
        "capability_id": capability_id,
        "matching_eligibility": eligibility,
        "verification_status": verification,
        "provides": ["solver.classification.predict"],
        "dependencies": [],
        "risk_gates": [],
    }


def artifacts(requirement=None, match_record=None, capabilities=None, intake=None):
    requirement = requirement or req()
    match_record = match_record or match(requirement["requirement_id"])
    requirements = build_requirements_artifact(
        [requirement],
        source_artifacts={"contest_spec": "contest_spec.json", "evidence_index": "evidence_index.json", "coverage": None},
    )
    matches = {
        "schema_version": "v0.10B",
        "artifact_type": "requirement_capability_match",
        "source_requirements": "contest_requirements.json",
        "source_capabilities": "capability_registry.json",
        "summary": build_match_summary(requirements["requirements"], [match_record]),
        "matches": [match_record],
        "unmatched_tokens": [],
        "warnings": [],
    }
    capabilities = {
        "schema_version": "v0.10A",
        "artifact_type": "capability_registry",
        "capabilities": capabilities or [cap()],
    }
    ledger = build_decision_ledger(requirements, matches, capabilities, intake)
    return requirements, matches, capabilities, ledger


def decision(requirement, match_record, *, action="implement_missing_capability", status="confirmed", supersedes=None, stale=False):
    return {
        "decision_id": "dec.solver.task_solution.r001" if supersedes is None else "dec.solver.task_solution.r002",
        "requirement_id": requirement["requirement_id"],
        "expected_subject_digest": "sha256:" + "9" * 64 if stale else build_subject_digest(requirement, match_record),
        "actor": "human",
        "decision_status": status,
        "action": action,
        "decision_value": None,
        "rationale": "Decision.",
        "selected_capability_ids": ["cap.solver.classification"] if action == "use_existing_capability" else [],
        "evidence_ids": [],
        "conditions": [],
        "supersedes": supersedes,
        "notes": [],
    }


def decision_intake(requirements, matches, capabilities, *decisions, source_digests=None):
    return {
        "schema_version": "v0.11A",
        "artifact_type": "decision_intake",
        "source_digests": source_digests
        or {
            "contest_requirements": canonical_json_digest(requirements),
            "requirement_capability_match": canonical_json_digest(matches),
            "capability_registry": canonical_json_digest(capabilities),
        },
        "decisions": list(decisions),
        "notes": [],
    }


def validation(*, passed=True, warning=False):
    checks = []
    if not passed:
        checks.append({"name": "rows", "passed": False, "severity": "error", "message": "/abs/path", "details": {"submission_path": "/tmp/x"}})
    if warning:
        checks.append({"name": "soft", "passed": False, "severity": "warning", "message": "/abs/path", "details": {"test_csv_path": "/tmp/y"}})
    return {"passed": passed, "error_count": 0 if passed else 1, "warning_count": 1 if warning else 0, "checks": checks}


def approval_intake(summary, status="approved", *, digest=None, second_leaf=False, conditions=None):
    entry = {
        "approval_id": "approval.local_submission_candidate.r001",
        "scope": "local_submission_candidate",
        "expected_readiness_digest": digest or summary["readiness_digest"],
        "actor": "human",
        "approval_status": status,
        "rationale": "Reviewed the current local artifacts and approve this local submission candidate." if status != "pending" else "",
        "conditions": conditions or ([] if status != "conditional" else ["Resolve item."]),
        "supersedes": None,
        "notes": [],
    }
    approvals = [entry]
    if second_leaf:
        other = copy.deepcopy(entry)
        other["approval_id"] = "approval.local_submission_candidate.r002"
        approvals.append(other)
    return {
        "schema_version": "v0.11B",
        "artifact_type": "human_approval_intake",
        "source_digests": copy.deepcopy(summary["source_digests"]),
        "readiness_digest": summary["readiness_digest"],
        "approvals": approvals,
        "notes": [],
    }


def summary_for(requirement=None, match_record=None, capabilities=None, intake=None, report=None, approval=None):
    requirements, matches, capabilities, ledger = artifacts(requirement, match_record, capabilities, intake)
    return build_human_approval_summary(
        requirements,
        matches,
        ledger,
        capabilities,
        validation_report=report,
        approval_intake=approval,
    )


def blocking_ids(summary):
    return set(summary["overall_gate"]["blocking_check_ids"])


def test_active_must_gap_and_accept_risk_do_not_become_ready():
    requirement = req()
    match_record = match(status="unmet")
    requirements, matches, capabilities, _ = artifacts(requirement, match_record)
    intake = decision_intake(requirements, matches, capabilities, decision(requirement, match_record, action="accept_risk"))
    summary = summary_for(requirement, match_record, intake=intake, report=validation())
    assert summary["machine_readiness"]["status"] == "blocked"
    assert "gate.requirements.active_must_gaps" in blocking_ids(summary)


@pytest.mark.parametrize(
    ("mutator", "check_id"),
    [
        (lambda r, m, c: None, "gate.decisions.unresolved_required"),
        (lambda r, m, c: decision_intake(r, m, c, decision(r["requirements"][0], m["matches"][0], stale=True)), "gate.decisions.stale"),
        (
            lambda r, m, c: decision_intake(
                r,
                m,
                c,
                decision(r["requirements"][0], m["matches"][0]),
                {**decision(r["requirements"][0], m["matches"][0]), "decision_id": "dec.solver.task_solution.r002"},
            ),
            "gate.decisions.conflicting",
        ),
        (
            lambda r, m, c: decision_intake(r, m, c, decision(r["requirements"][0], m["matches"][0], action="implement_missing_capability")),
            "gate.decisions.follow_up_required",
        ),
    ],
)
def test_decision_blockers(mutator, check_id):
    requirement = req()
    match_record = match(status="unmet")
    requirements, matches, capabilities, _ = artifacts(requirement, match_record)
    intake = mutator(requirements, matches, capabilities)
    summary = summary_for(requirement, match_record, intake=intake, report=validation())
    assert check_id in blocking_ids(summary)


def test_ledger_source_and_subject_drift_are_blockers():
    requirement = req()
    match_record = match(status="satisfied")
    requirements, matches, capabilities, ledger = artifacts(requirement, match_record)
    source_drift = copy.deepcopy(ledger)
    source_drift["source_digests"]["contest_requirements"] = "sha256:" + "8" * 64
    summary = build_human_approval_summary(requirements, matches, source_drift, capabilities, validation_report=validation())
    assert "gate.ledger.source_digests_current" in blocking_ids(summary)

    subject_drift = copy.deepcopy(ledger)
    subject_drift["records"][0]["subject_digest"] = "sha256:" + "7" * 64
    summary = build_human_approval_summary(requirements, matches, subject_drift, capabilities, validation_report=validation())
    assert "gate.ledger.subjects_current" in blocking_ids(summary)


def test_required_capability_health_and_unrelated_planned_capability():
    requirement = req(risk_level="green")
    good = summary_for(requirement, match(status="satisfied"), capabilities=[cap(), cap("cap.unrelated", verification="not_applicable", eligibility="ineligible")], report=validation())
    assert "gate.capabilities.required_health" not in blocking_ids(good)

    limited = summary_for(requirement, match(status="satisfied"), capabilities=[cap(eligibility="limited")], report=validation())
    assert "gate.capabilities.required_health" in blocking_ids(limited)
    incomplete = summary_for(requirement, match(status="satisfied"), capabilities=[cap(verification="incomplete")], report=validation())
    assert "gate.capabilities.required_health" in blocking_ids(incomplete)


def test_validation_report_presence_failure_warning_and_sanitization():
    requirement = req(risk_level="green")
    no_report = summary_for(requirement, match(status="satisfied"))
    assert "gate.validation.present" in blocking_ids(no_report)
    failed = summary_for(requirement, match(status="satisfied"), report=validation(passed=False))
    assert "gate.validation.passed" in blocking_ids(failed)
    payload = json.dumps(failed, sort_keys=True)
    assert "/abs/path" not in payload
    assert "submission_path" not in payload
    warned = summary_for(requirement, match(status="satisfied"), report=validation(warning=True))
    assert warned["machine_readiness"]["status"] == "reviewable"
    assert "gate.validation.warnings" in {c["check_id"] for c in warned["machine_readiness"]["checks"] if c["status"] == "warning"}


def test_overall_gate_approval_states_and_blocker_override():
    reviewable = summary_for(req(risk_level="green"), match(status="satisfied"), report=validation())
    assert reviewable["machine_readiness"]["status"] == "reviewable"
    assert reviewable["overall_gate"]["status"] == "awaiting_human_approval"

    approved = summary_for(req(risk_level="green"), match(status="satisfied"), report=validation(), approval=approval_intake(reviewable, "approved"))
    assert approved["human_approval"]["approval_granted"] is True
    assert approved["overall_gate"]["status"] == "approved"

    rejected = summary_for(req(risk_level="green"), match(status="satisfied"), report=validation(), approval=approval_intake(reviewable, "rejected"))
    assert rejected["overall_gate"]["status"] == "rejected"
    conditional = summary_for(req(risk_level="green"), match(status="satisfied"), report=validation(), approval=approval_intake(reviewable, "conditional"))
    assert conditional["overall_gate"]["status"] == "conditional_approval"
    stale = summary_for(req(risk_level="green"), match(status="satisfied"), report=validation(), approval=approval_intake(reviewable, "approved", digest="sha256:" + "9" * 64))
    assert stale["overall_gate"]["status"] == "stale_approval"
    conflict = summary_for(req(risk_level="green"), match(status="satisfied"), report=validation(), approval=approval_intake(reviewable, "approved", second_leaf=True))
    assert conflict["overall_gate"]["status"] == "conflicting_approval"

    blocked_base = summary_for(req(), match(status="unmet"), report=validation())
    blocked = summary_for(req(), match(status="unmet"), report=validation(), approval=approval_intake(blocked_base, "approved"))
    assert blocked["overall_gate"]["status"] == "blocked"
    assert "Human approval cannot override machine readiness blockers." in blocked["warnings"]


def test_template_generation_rules_and_markdown_caveats():
    blocked = summary_for(req(), match(status="unmet"), report=validation())
    assert build_human_approval_intake_template(blocked)["approvals"] == []

    reviewable = summary_for(req(risk_level="green"), match(status="satisfied"), report=validation())
    template = build_human_approval_intake_template(reviewable)
    assert template["approvals"][0]["approval_id"] == "approval.local_submission_candidate.r001"
    assert template["approvals"][0]["expected_readiness_digest"] == reviewable["readiness_digest"]

    pending = copy.deepcopy(template)
    approved = copy.deepcopy(template)
    approved["approvals"][0].update({"approval_status": "approved", "rationale": "Approved."})
    rejected = copy.deepcopy(template)
    rejected["approvals"][0].update({"approval_status": "rejected", "rationale": "Rejected."})
    conditional = copy.deepcopy(template)
    conditional["approvals"][0].update({"approval_status": "conditional", "rationale": "Conditional.", "conditions": ["x"]})
    for intake, expected_len in [(pending, 1), (conditional, 1), (approved, 0), (rejected, 0)]:
        summary = summary_for(req(risk_level="green"), match(status="satisfied"), report=validation(), approval=intake)
        next_template = build_human_approval_intake_template(summary)
        assert len(next_template["approvals"]) == expected_len
        if expected_len:
            assert next_template["approvals"][0]["supersedes"] == "approval.local_submission_candidate.r001"

    markdown = render_human_approval_summary_markdown(reviewable)
    assert "Human Approval은 blocker를 덮어쓰지 않는다." in markdown
    assert "공식 대회 규칙 확인" in markdown


def test_summary_is_deterministic_and_has_no_timestamp_or_absolute_path():
    summary = summary_for(req(risk_level="green"), match(status="satisfied"), report=validation(warning=True))
    again = summary_for(req(risk_level="green"), match(status="satisfied"), report=validation(warning=True))
    assert summary == again
    payload = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    assert "timestamp" not in payload
    assert "created_at" not in payload
    assert "/mnt/" not in payload
    assert "/tmp/" not in payload
