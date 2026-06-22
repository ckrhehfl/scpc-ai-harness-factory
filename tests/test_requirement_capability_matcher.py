from __future__ import annotations

from factory.requirement_model import build_requirements_artifact
from factory.requirement_capability_matcher import match_requirements_to_capabilities


def req(requirement_id, tokens, *, requirement_type="capability", applicability="active", priority="must"):
    return {
        "requirement_id": requirement_id,
        "title": requirement_id,
        "origin": "contest_spec",
        "domain": "runtime",
        "requirement_type": requirement_type,
        "priority": priority,
        "provenance_status": "observed" if applicability == "active" else "unknown",
        "applicability": applicability,
        "risk_level": "green",
        "required_tokens": tokens,
        "parameters": {},
        "source_refs": [{"artifact": "contest_spec.json", "path": "x.y"}],
        "evidence_ids": [],
        "notes": [],
    }


def cap(capability_id, provides, *, eligibility="eligible", dependencies=None, risk_gates=None):
    return {
        "capability_id": capability_id,
        "matching_eligibility": eligibility,
        "provides": provides,
        "dependencies": dependencies or [],
        "risk_gates": risk_gates or [],
    }


def requirements(*items):
    return build_requirements_artifact(
        list(items),
        source_artifacts={"contest_spec": "generated/contest_spec.json", "evidence_index": "generated/evidence_index.json", "coverage": None},
    )


def registry(*capabilities):
    return {
        "schema_version": "v0.10A",
        "artifact_type": "capability_registry",
        "capabilities": list(capabilities),
    }


def match_by_id(artifact):
    return {item["requirement_id"]: item for item in artifact["matches"]}


def test_exact_token_satisfied_without_substring_or_case_matching():
    artifact = match_requirements_to_capabilities(
        requirements(
            req("req.runtime.good", ["submission.csv.write"]),
            req("req.runtime.substring", ["submission.csv"]),
            req("req.runtime.case", ["case.token"]),
        ),
        registry(cap("cap.good", ["submission.csv.write", "xsubmission.csvx"]), cap("cap.case", ["Case.Token"])),
        {},
    )
    matches = match_by_id(artifact)
    assert matches["req.runtime.good"]["match_status"] == "satisfied"
    assert matches["req.runtime.substring"]["match_status"] == "unmet"
    assert matches["req.runtime.case"]["match_status"] == "unmet"


def test_partial_unmet_limited_and_ineligible_provider_policy():
    artifact = match_requirements_to_capabilities(
        requirements(
            req("req.runtime.partial", ["a.good", "a.missing"]),
            req("req.runtime.limited", ["a.limited"]),
            req("req.runtime.ineligible", ["a.ineligible"]),
            req("req.runtime.none", ["a.none"]),
        ),
        registry(
            cap("cap.good", ["a.good"]),
            cap("cap.limited", ["a.limited"], eligibility="limited"),
            cap("cap.ineligible", ["a.ineligible"], eligibility="ineligible"),
        ),
        {},
    )
    matches = match_by_id(artifact)
    assert matches["req.runtime.partial"]["match_status"] == "partial"
    assert matches["req.runtime.limited"]["match_status"] == "partial"
    assert matches["req.runtime.ineligible"]["match_status"] == "unmet"
    assert matches["req.runtime.none"]["match_status"] == "unmet"
    assert artifact["unmatched_tokens"] == ["a.ineligible", "a.missing", "a.none"]


def test_dependencies_are_transitive_and_can_limit_or_block():
    artifact = match_requirements_to_capabilities(
        requirements(
            req("req.runtime.dep_limited", ["a.top"]),
            req("req.runtime.dep_blocked", ["b.top"]),
        ),
        registry(
            cap("cap.dep.limited", ["dep.limited"], eligibility="limited"),
            cap("cap.top", ["a.top"], dependencies=["cap.dep.limited"]),
            cap("cap.dep.ineligible", ["dep.ineligible"], eligibility="ineligible"),
            cap("cap.blocked", ["b.top"], dependencies=["cap.dep.ineligible"]),
        ),
        {},
    )
    matches = match_by_id(artifact)
    assert matches["req.runtime.dep_limited"]["match_status"] == "partial"
    assert matches["req.runtime.dep_limited"]["dependency_capability_ids"] == ["cap.dep.limited"]
    assert matches["req.runtime.dep_blocked"]["match_status"] == "blocked"
    assert "cap.dep.ineligible" in matches["req.runtime.dep_blocked"]["dependency_capability_ids"]


def test_risk_gates_block_until_allowed():
    gated = registry(cap("cap.gated", ["a.gated"], risk_gates=["rules.external_api_allowed"]))
    blocked = match_requirements_to_capabilities(
        requirements(req("req.runtime.gated", ["a.gated"])),
        gated,
        {"rules": {"external_api_allowed": "unknown"}},
    )
    allowed = match_requirements_to_capabilities(
        requirements(req("req.runtime.gated", ["a.gated"])),
        gated,
        {"rules": {"external_api_allowed": "allowed"}},
    )
    assert match_by_id(blocked)["req.runtime.gated"]["match_status"] == "blocked"
    assert match_by_id(allowed)["req.runtime.gated"]["match_status"] == "satisfied"


def test_constraints_prohibitions_pending_capability_and_summary_counts():
    artifact = match_requirements_to_capabilities(
        requirements(
            req("req.runtime.pending", ["a.good"], applicability="pending"),
            req("req.governance.constraint", [], requirement_type="constraint"),
            req("req.governance.prohibition", [], requirement_type="prohibition"),
        ),
        registry(cap("cap.good", ["a.good"])),
        {},
    )
    matches = match_by_id(artifact)
    assert matches["req.runtime.pending"]["match_status"] == "blocked"
    assert matches["req.governance.constraint"]["match_status"] == "not_evaluated"
    assert matches["req.governance.prohibition"]["match_status"] == "not_evaluated"
    assert artifact["summary"]["blocked"] == 1
    assert artifact["summary"]["not_evaluated"] == 2


def test_duplicate_provider_ids_are_deduped_and_output_is_deterministic():
    reqs = requirements(req("req.runtime.dupes", ["a.dupe"]))
    reg = registry(
        cap("cap.a", ["a.dupe"], dependencies=["cap.dep"]),
        cap("cap.dep", ["dep.token"]),
    )
    first = match_requirements_to_capabilities(reqs, reg, {})
    second = match_requirements_to_capabilities(reqs, reg, {})
    match = first["matches"][0]
    assert match["matched_capability_ids"] == ["cap.a"]
    assert match["dependency_capability_ids"] == ["cap.dep"]
    assert first == second
