from __future__ import annotations

import copy
import json
import pytest

from factory.decision_ledger_builder import (
    build_decision_intake_template,
    build_decision_ledger,
    render_decision_ledger_markdown,
)
from factory.decision_model import DecisionModelError, build_subject_digest, canonical_json_digest
from factory.requirement_model import build_match_summary, build_requirements_artifact


def req(
    requirement_id="req.solver.task_solution",
    *,
    priority="must",
    applicability="active",
    risk_level="red",
    provenance_status="observed",
    requirement_type="capability",
    required_tokens=None,
    evidence_ids=None,
):
    return {
        "requirement_id": requirement_id,
        "title": requirement_id,
        "origin": "contest_spec",
        "domain": "solver",
        "requirement_type": requirement_type,
        "priority": priority,
        "provenance_status": provenance_status,
        "applicability": applicability,
        "risk_level": risk_level,
        "required_tokens": ["solver.classification.predict"] if required_tokens is None else required_tokens,
        "parameters": {},
        "source_refs": [{"artifact": "contest_spec.json", "path": "problem"}],
        "evidence_ids": ["ev_0123456789abcdef"] if evidence_ids is None else evidence_ids,
        "notes": [],
    }


def match(requirement_id="req.solver.task_solution", *, status="unmet", matched=None, missing=None):
    return {
        "requirement_id": requirement_id,
        "match_status": status,
        "required_tokens": ["solver.classification.predict"],
        "token_matches": [
            {
                "token": "solver.classification.predict",
                "eligible_capability_ids": matched or [],
                "limited_capability_ids": [],
                "ineligible_capability_ids": [],
                "blocked_capability_ids": [],
            }
        ],
        "matched_capability_ids": matched or [],
        "dependency_capability_ids": [],
        "missing_tokens": ["solver.classification.predict"] if missing is None else missing,
        "blocked_by": [],
        "notes": [],
    }


def artifacts(*requirements, matches=None, capabilities=None):
    requirements_artifact = build_requirements_artifact(
        list(requirements) or [req()],
        source_artifacts={"contest_spec": "contest_spec.json", "evidence_index": "evidence_index.json", "coverage": None},
    )
    match_items = matches or [match()]
    matches_artifact = {
        "schema_version": "v0.10B",
        "artifact_type": "requirement_capability_match",
        "source_requirements": "contest_requirements.json",
        "source_capabilities": "capability_registry.json",
        "summary": build_match_summary(requirements_artifact["requirements"], match_items),
        "matches": sorted(match_items, key=lambda item: item["requirement_id"]),
        "unmatched_tokens": [],
        "warnings": [],
    }
    registry = {
        "schema_version": "v0.10A",
        "artifact_type": "capability_registry",
        "capabilities": capabilities
        if capabilities is not None
        else [cap("cap.solver.classification", ["solver.classification.predict"])],
    }
    return requirements_artifact, matches_artifact, registry


def cap(capability_id, provides):
    return {
        "capability_id": capability_id,
        "matching_eligibility": "eligible",
        "provides": provides,
        "dependencies": [],
        "risk_gates": [],
    }


def intake_for(requirements, matches, capabilities, *decisions, source_digests=None):
    digests = source_digests or {
        "contest_requirements": canonical_json_digest(requirements),
        "requirement_capability_match": canonical_json_digest(matches),
        "capability_registry": canonical_json_digest(capabilities),
    }
    return {
        "schema_version": "v0.11A",
        "artifact_type": "decision_intake",
        "source_digests": digests,
        "decisions": list(decisions),
        "notes": [],
    }


def decision(requirement, match_record, **overrides):
    requirement_id = requirement["requirement_id"]
    stem = requirement_id.removeprefix("req.")
    entry = {
        "decision_id": f"dec.{stem}.r001",
        "requirement_id": requirement_id,
        "expected_subject_digest": build_subject_digest(requirement, match_record),
        "actor": "human",
        "decision_status": "confirmed",
        "action": "implement_missing_capability",
        "decision_value": None,
        "rationale": "Do it.",
        "selected_capability_ids": [],
        "evidence_ids": list(requirement["evidence_ids"]),
        "conditions": [],
        "supersedes": None,
        "notes": [],
    }
    entry.update(overrides)
    return entry


def record(ledger, requirement_id="req.solver.task_solution"):
    return {item["requirement_id"]: item for item in ledger["records"]}[requirement_id]


def test_no_intake_required_is_pending_and_not_required_is_not_required():
    required, required_match, caps = artifacts(req(), matches=[match()])
    ledger = build_decision_ledger(required, required_match, caps)
    assert record(ledger)["resolution_status"] == "pending"
    assert record(ledger)["decision_required_reasons"] == ["active_must_gap"]

    not_required_req = req(priority="should", applicability="active", risk_level="green")
    reqs, matches, caps = artifacts(not_required_req, matches=[match(status="satisfied", matched=["cap.solver.classification"], missing=[])])
    ledger = build_decision_ledger(reqs, matches, caps)
    assert record(ledger)["resolution_status"] == "not_required"


def test_human_confirmed_is_authoritative_and_ai_proposal_or_rejected_are_not():
    reqs, matches, caps = artifacts(req(), matches=[match()])
    base_decision = decision(reqs["requirements"][0], matches["matches"][0])
    confirmed = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, base_decision))
    assert record(confirmed)["resolution_status"] == "confirmed"
    assert record(confirmed)["authoritative"] is True

    ai = copy.deepcopy(base_decision)
    ai.update({"actor": "ai", "decision_status": "proposed", "rationale": "Candidate."})
    proposed = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, ai))
    assert record(proposed)["resolution_status"] == "proposed"
    assert record(proposed)["authoritative"] is False

    rejected_entry = copy.deepcopy(base_decision)
    rejected_entry.update({"decision_status": "rejected", "action": "implement_missing_capability", "rationale": "Reject proposal."})
    rejected = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, rejected_entry))
    assert record(rejected)["resolution_status"] == "rejected"
    assert record(rejected)["authoritative"] is False


def test_subject_digest_mismatch_is_stale_and_source_digest_mismatch_warns():
    reqs, matches, caps = artifacts(req(), matches=[match()])
    stale_decision = decision(reqs["requirements"][0], matches["matches"][0], expected_subject_digest="sha256:" + "9" * 64)
    wrong_sources = {
        "contest_requirements": "sha256:" + "1" * 64,
        "requirement_capability_match": canonical_json_digest(matches),
        "capability_registry": canonical_json_digest(caps),
    }
    ledger = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, stale_decision, source_digests=wrong_sources))
    assert record(ledger)["resolution_status"] == "stale"
    assert ledger["warnings"] == ["Decision intake source digest mismatch for contest_requirements."]


def test_stale_previous_record_can_be_superseded_by_current_decision():
    reqs, matches, caps = artifacts(req(), matches=[match()])
    old = decision(
        reqs["requirements"][0],
        matches["matches"][0],
        actor="ai",
        decision_status="proposed",
        rationale="Old.",
        expected_subject_digest="sha256:" + "9" * 64,
    )
    new = decision(
        reqs["requirements"][0],
        matches["matches"][0],
        decision_id="dec.solver.task_solution.r002",
        supersedes=old["decision_id"],
    )
    ledger = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, new, old))
    assert record(ledger)["resolution_status"] == "confirmed"
    assert [item["decision_id"] for item in record(ledger)["history"]] == [old["decision_id"], new["decision_id"]]


def test_use_existing_must_match_current_match_or_becomes_conflicting():
    reqs, matches, caps = artifacts(
        req(),
        matches=[match(status="satisfied", matched=["cap.solver.classification"], missing=[])],
    )
    ok = decision(
        reqs["requirements"][0],
        matches["matches"][0],
        action="use_existing_capability",
        selected_capability_ids=["cap.solver.classification"],
        rationale="Use it.",
    )
    ledger = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, ok))
    assert record(ledger)["resolution_status"] == "confirmed"

    bad = copy.deepcopy(ok)
    bad["selected_capability_ids"] = ["cap.other.solver"]
    caps["capabilities"].append(cap("cap.other.solver", ["solver.classification.predict"]))
    ledger = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, bad))
    assert record(ledger)["resolution_status"] == "conflicting"


def test_unknown_selected_capability_is_structural_error():
    reqs, matches, caps = artifacts(req(), matches=[match()])
    item = decision(
        reqs["requirements"][0],
        matches["matches"][0],
        action="use_existing_capability",
        selected_capability_ids=["cap.unknown"],
        rationale="Use it.",
    )
    with pytest.raises(DecisionModelError):
        build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, item))


@pytest.mark.parametrize(
    ("action", "value", "follow_up"),
    [
        ("implement_missing_capability", None, True),
        ("confirm_value", "allowed", True),
        ("wait_for_information", None, True),
        ("accept_risk", None, False),
        ("waive_requirement", None, False),
        ("reject_requirement", None, False),
    ],
)
def test_confirmed_action_follow_up_classification(action, value, follow_up):
    reqs, matches, caps = artifacts(req(), matches=[match()])
    item = decision(reqs["requirements"][0], matches["matches"][0], action=action, decision_value=value, rationale="Rationale.")
    ledger = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, item))
    assert record(ledger)["resolution_status"] == "confirmed"
    assert record(ledger)["follow_up_required"] is follow_up


def test_summary_sorting_determinism_and_no_paths_or_timestamps():
    req_a = req("req.solver.a")
    req_b = req("req.solver.b", priority="should", risk_level="green")
    matches = [match("req.solver.b", status="satisfied", matched=["cap.solver.classification"], missing=[]), match("req.solver.a")]
    reqs, match_artifact, caps = artifacts(req_b, req_a, matches=matches)
    ledger = build_decision_ledger(reqs, match_artifact, caps)
    assert [item["requirement_id"] for item in ledger["records"]] == ["req.solver.a", "req.solver.b"]
    assert ledger == build_decision_ledger(reqs, match_artifact, caps)
    payload = json.dumps(ledger, ensure_ascii=False, sort_keys=True)
    assert "/tmp/" not in payload
    assert "created_at" not in payload
    assert "timestamp" not in payload
    assert ledger["summary"]["total"] == 2


def test_template_includes_only_required_unresolved_and_sets_revision_and_supersedes():
    reqs, matches, caps = artifacts(req(), matches=[match()])
    ai = decision(reqs["requirements"][0], matches["matches"][0], actor="ai", decision_status="proposed", rationale="Candidate.")
    ledger = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, ai))
    template = build_decision_intake_template(ledger)
    assert len(template["decisions"]) == 1
    entry = template["decisions"][0]
    assert entry["decision_id"] == "dec.solver.task_solution.r002"
    assert entry["supersedes"] == ai["decision_id"]
    assert entry["decision_status"] == "pending"
    assert entry["action"] == "no_action"
    assert entry["evidence_ids"] == ["ev_0123456789abcdef"]


def test_template_skips_confirmed_not_required_and_conflict():
    reqs, matches, caps = artifacts(req(), matches=[match()])
    one = decision(reqs["requirements"][0], matches["matches"][0])
    two = decision(reqs["requirements"][0], matches["matches"][0], decision_id="dec.solver.task_solution.r002")
    conflict = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, one, two))
    template = build_decision_intake_template(conflict)
    assert template["decisions"] == []
    assert template["notes"] == ["Manual conflict resolution is required for req.solver.task_solution."]

    confirmed = build_decision_ledger(reqs, matches, caps, intake_for(reqs, matches, caps, one))
    assert build_decision_intake_template(confirmed)["decisions"] == []

    not_required_req = req(priority="should", risk_level="green")
    reqs2, matches2, caps2 = artifacts(not_required_req, matches=[match(status="satisfied", matched=["cap.solver.classification"], missing=[])])
    assert build_decision_intake_template(build_decision_ledger(reqs2, matches2, caps2))["decisions"] == []


def test_markdown_contains_required_disclaimers():
    reqs, matches, caps = artifacts(req(), matches=[match()])
    markdown = render_decision_ledger_markdown(build_decision_ledger(reqs, matches, caps))
    assert "Decision Ledger는 requirement 및 capability match에 대한 사람/AI의 disposition 기록이다." in markdown
    assert "Human Approval" in markdown
