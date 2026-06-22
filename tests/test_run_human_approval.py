from __future__ import annotations

from pathlib import Path
import copy
import json
import subprocess
import sys

from factory.decision_ledger_builder import build_decision_ledger
from factory.requirement_model import build_match_summary, build_requirements_artifact
from factory.utils import write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "factory" / "run_human_approval.py"


def req(*, risk_level="green"):
    return {
        "requirement_id": "req.solver.task_solution",
        "title": "Task solver",
        "origin": "contest_spec",
        "domain": "solver",
        "requirement_type": "capability",
        "priority": "must",
        "provenance_status": "observed",
        "applicability": "active",
        "risk_level": risk_level,
        "required_tokens": ["solver.classification.predict"],
        "parameters": {},
        "source_refs": [{"artifact": "contest_spec.json", "path": "problem"}],
        "evidence_ids": [],
        "notes": [],
    }


def match(*, status="satisfied"):
    matched = ["cap.solver.classification"] if status == "satisfied" else []
    return {
        "requirement_id": "req.solver.task_solution",
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
        "dependency_capability_ids": [],
        "missing_tokens": [] if status == "satisfied" else ["solver.classification.predict"],
        "blocked_by": [],
        "notes": [],
    }


def caps():
    return {
        "schema_version": "v0.10A",
        "artifact_type": "capability_registry",
        "capabilities": [
            {
                "capability_id": "cap.solver.classification",
                "matching_eligibility": "eligible",
                "verification_status": "verified",
                "provides": ["solver.classification.predict"],
                "dependencies": [],
                "risk_gates": [],
            }
        ],
    }


def validation_report():
    return {"passed": True, "error_count": 0, "warning_count": 0, "checks": []}


def make_inputs(tmp_path: Path, *, reviewable=True, validation=True):
    generated = tmp_path / "generated"
    requirement = req(risk_level="green" if reviewable else "red")
    match_record = match(status="satisfied" if reviewable else "unmet")
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
    capabilities = caps()
    ledger = build_decision_ledger(requirements, matches, capabilities)
    write_json(generated / "contest_requirements.json", requirements)
    write_json(generated / "requirement_capability_match.json", matches)
    write_json(generated / "decision_ledger.json", ledger)
    write_json(generated / "capability_registry.json", capabilities)
    if validation:
        write_json(generated / "validation_report.json", validation_report())
    return generated


def run_cli(generated: Path, *extra: str):
    args = [
        sys.executable,
        str(SCRIPT),
        "--requirements",
        str(generated / "contest_requirements.json"),
        "--matches",
        str(generated / "requirement_capability_match.json"),
        "--decision-ledger",
        str(generated / "decision_ledger.json"),
        "--capabilities",
        str(generated / "capability_registry.json"),
        "--output",
        str(generated),
        *extra,
    ]
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, check=False)


def add_validation(generated: Path):
    return ("--validation-report", str(generated / "validation_report.json"))


def write_approval(generated: Path, status: str, *, stale=False, conflict=False) -> Path:
    summary = json.loads((generated / "human_approval_summary.json").read_text(encoding="utf-8"))
    entry = {
        "approval_id": "approval.local_submission_candidate.r001",
        "scope": "local_submission_candidate",
        "expected_readiness_digest": "sha256:" + "9" * 64 if stale else summary["readiness_digest"],
        "actor": "human",
        "approval_status": status,
        "rationale": "Reviewed the current local artifacts and approve this local submission candidate." if status != "pending" else "",
        "conditions": ["Resolve condition."] if status == "conditional" else [],
        "supersedes": None,
        "notes": [],
    }
    approvals = [entry]
    if conflict:
        other = copy.deepcopy(entry)
        other["approval_id"] = "approval.local_submission_candidate.r002"
        approvals.append(other)
    intake = {
        "schema_version": "v0.11B",
        "artifact_type": "human_approval_intake",
        "source_digests": summary["source_digests"],
        "readiness_digest": summary["readiness_digest"],
        "approvals": approvals,
        "notes": [],
    }
    path = generated / f"approval_{status}.json"
    write_json(path, intake)
    return path


def test_blocked_reviewable_and_approval_exit_codes(tmp_path):
    blocked = make_inputs(tmp_path / "blocked", reviewable=False)
    result = run_cli(blocked, *add_validation(blocked))
    assert result.returncode == 2
    assert json.loads((blocked / "human_approval_summary.json").read_text(encoding="utf-8"))["overall_gate"]["status"] == "blocked"

    generated = make_inputs(tmp_path / "reviewable", reviewable=True)
    result = run_cli(generated, *add_validation(generated))
    assert result.returncode == 2
    assert json.loads((generated / "human_approval_summary.json").read_text(encoding="utf-8"))["overall_gate"]["status"] == "awaiting_human_approval"

    for status, expected_exit, expected_gate in [
        ("approved", 0, "approved"),
        ("rejected", 2, "rejected"),
        ("conditional", 2, "conditional_approval"),
    ]:
        approval = write_approval(generated, status)
        result = run_cli(generated, *add_validation(generated), "--approval-intake", str(approval))
        assert result.returncode == expected_exit
        summary = json.loads((generated / "human_approval_summary.json").read_text(encoding="utf-8"))
        assert summary["overall_gate"]["status"] == expected_gate


def test_stale_conflicting_and_missing_validation_exit_2(tmp_path):
    generated = make_inputs(tmp_path, reviewable=True, validation=True)
    assert run_cli(generated, *add_validation(generated)).returncode == 2
    stale = write_approval(generated, "approved", stale=True)
    assert run_cli(generated, *add_validation(generated), "--approval-intake", str(stale)).returncode == 2
    assert json.loads((generated / "human_approval_summary.json").read_text(encoding="utf-8"))["overall_gate"]["status"] == "stale_approval"
    conflict = write_approval(generated, "approved", conflict=True)
    assert run_cli(generated, *add_validation(generated), "--approval-intake", str(conflict)).returncode == 2
    assert json.loads((generated / "human_approval_summary.json").read_text(encoding="utf-8"))["overall_gate"]["status"] == "conflicting_approval"

    no_validation = make_inputs(tmp_path / "no_validation", reviewable=True, validation=False)
    assert run_cli(no_validation).returncode == 2
    assert "gate.validation.present" in json.loads((no_validation / "human_approval_summary.json").read_text(encoding="utf-8"))["overall_gate"]["blocking_check_ids"]


def test_malformed_inputs_exit_1_without_outputs(tmp_path):
    generated = make_inputs(tmp_path, reviewable=True)
    (generated / "validation_report.json").write_text('{"passed": true, "error_count": 1, "warning_count": 0, "checks": []}', encoding="utf-8")
    assert run_cli(generated, *add_validation(generated)).returncode == 1
    assert not (generated / "human_approval_summary.json").exists()

    generated = make_inputs(tmp_path / "bad_approval", reviewable=True)
    bad_approval = generated / "bad_approval.json"
    bad_approval.write_text("{bad", encoding="utf-8")
    assert run_cli(generated, *add_validation(generated), "--approval-intake", str(bad_approval)).returncode == 1
    assert not (generated / "human_approval_summary.json").exists()

    for filename in ["contest_requirements.json", "requirement_capability_match.json", "decision_ledger.json", "capability_registry.json"]:
        generated = make_inputs(tmp_path / filename, reviewable=True)
        (generated / filename).write_text("{bad", encoding="utf-8")
        assert run_cli(generated, *add_validation(generated)).returncode == 1
        assert not (generated / "human_approval_summary.json").exists()


def test_deterministic_rerun_sources_unchanged_and_no_absolute_input_paths(tmp_path):
    generated = make_inputs(tmp_path, reviewable=True)
    before = {path.name: path.read_bytes() for path in generated.glob("*.json")}
    first = run_cli(generated, *add_validation(generated))
    first_summary = (generated / "human_approval_summary.json").read_bytes()
    first_template = (generated / "human_approval_intake_template.json").read_bytes()
    second = run_cli(generated, *add_validation(generated))
    assert first.returncode == 2
    assert second.returncode == 2
    assert first_summary == (generated / "human_approval_summary.json").read_bytes()
    assert first_template == (generated / "human_approval_intake_template.json").read_bytes()
    for name, payload in before.items():
        assert (generated / name).read_bytes() == payload
    assert str(tmp_path) not in (generated / "human_approval_summary.json").read_text(encoding="utf-8")
