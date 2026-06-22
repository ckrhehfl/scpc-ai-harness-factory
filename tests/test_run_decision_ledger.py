from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

from factory.decision_model import build_subject_digest, canonical_json_digest
from factory.requirement_model import build_match_summary, build_requirements_artifact
from factory.utils import write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "factory" / "run_decision_ledger.py"


def req():
    return {
        "requirement_id": "req.solver.task_solution",
        "title": "Task solver",
        "origin": "contest_spec",
        "domain": "solver",
        "requirement_type": "capability",
        "priority": "must",
        "provenance_status": "observed",
        "applicability": "active",
        "risk_level": "red",
        "required_tokens": ["solver.classification.predict"],
        "parameters": {},
        "source_refs": [{"artifact": "contest_spec.json", "path": "problem"}],
        "evidence_ids": [],
        "notes": [],
    }


def match(status="unmet"):
    return {
        "requirement_id": "req.solver.task_solution",
        "match_status": status,
        "required_tokens": ["solver.classification.predict"],
        "token_matches": [
            {
                "token": "solver.classification.predict",
                "eligible_capability_ids": [],
                "limited_capability_ids": [],
                "ineligible_capability_ids": [],
                "blocked_capability_ids": [],
            }
        ],
        "matched_capability_ids": [],
        "dependency_capability_ids": [],
        "missing_tokens": ["solver.classification.predict"],
        "blocked_by": [],
        "notes": [],
    }


def capability_registry():
    return {
        "schema_version": "v0.10A",
        "artifact_type": "capability_registry",
        "capabilities": [
            {
                "capability_id": "cap.solver.classification",
                "matching_eligibility": "eligible",
                "provides": ["solver.classification.predict"],
                "dependencies": [],
                "risk_gates": [],
            }
        ],
    }


def make_inputs(tmp_path):
    generated = tmp_path / "generated"
    requirement = req()
    match_record = match()
    requirements = build_requirements_artifact(
        [requirement],
        source_artifacts={"contest_spec": "contest_spec.json", "evidence_index": "evidence_index.json", "coverage": None},
    )
    matches = {
        "schema_version": "v0.10B",
        "artifact_type": "requirement_capability_match",
        "source_requirements": "contest_requirements.json",
        "source_capabilities": "capability_registry.json",
        "summary": build_match_summary([requirement], [match_record]),
        "matches": [match_record],
        "unmatched_tokens": [],
        "warnings": [],
    }
    capabilities = capability_registry()
    write_json(generated / "contest_requirements.json", requirements)
    write_json(generated / "requirement_capability_match.json", matches)
    write_json(generated / "capability_registry.json", capabilities)
    return generated, requirements, matches, capabilities


def run_cli(generated, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--requirements",
            str(generated / "contest_requirements.json"),
            "--matches",
            str(generated / "requirement_capability_match.json"),
            "--capabilities",
            str(generated / "capability_registry.json"),
            "--output",
            str(generated),
            *extra,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def confirmed_intake(requirements, matches, capabilities, *, stale=False, source_mismatch=False):
    requirement = requirements["requirements"][0]
    match_record = matches["matches"][0]
    digests = {
        "contest_requirements": canonical_json_digest(requirements),
        "requirement_capability_match": canonical_json_digest(matches),
        "capability_registry": canonical_json_digest(capabilities),
    }
    if source_mismatch:
        digests["contest_requirements"] = "sha256:" + "1" * 64
    return {
        "schema_version": "v0.11A",
        "artifact_type": "decision_intake",
        "source_digests": digests,
        "decisions": [
            {
                "decision_id": "dec.solver.task_solution.r001",
                "requirement_id": "req.solver.task_solution",
                "expected_subject_digest": "sha256:" + "9" * 64 if stale else build_subject_digest(requirement, match_record),
                "actor": "human",
                "decision_status": "confirmed",
                "action": "implement_missing_capability",
                "decision_value": None,
                "rationale": "Implement a task-specific solver before final submission.",
                "selected_capability_ids": [],
                "evidence_ids": [],
                "conditions": [],
                "supersedes": None,
                "notes": [],
            }
        ],
        "notes": [],
    }


def test_no_intake_required_pending_exit_2_outputs_and_input_unchanged(tmp_path):
    generated, _, _, _ = make_inputs(tmp_path)
    before = {path.name: path.read_bytes() for path in generated.glob("*.json")}
    result = run_cli(generated)
    assert result.returncode == 2
    assert "[OK] Decision ledger generated" in result.stdout
    assert (generated / "decision_ledger.json").exists()
    assert (generated / "decision_ledger.md").exists()
    assert (generated / "decision_intake_template.json").exists()
    for name, payload in before.items():
        assert (generated / name).read_bytes() == payload
    output_payload = (generated / "decision_ledger.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in output_payload


def test_all_required_human_confirmed_exit_0_and_deterministic(tmp_path):
    generated, requirements, matches, capabilities = make_inputs(tmp_path)
    intake_path = tmp_path / "decision_intake.json"
    write_json(intake_path, confirmed_intake(requirements, matches, capabilities))
    result = run_cli(generated, "--intake", str(intake_path))
    assert result.returncode == 0
    first_ledger = (generated / "decision_ledger.json").read_bytes()
    first_template = (generated / "decision_intake_template.json").read_bytes()
    second = run_cli(generated, "--intake", str(intake_path))
    assert second.returncode == 0
    assert first_ledger == (generated / "decision_ledger.json").read_bytes()
    assert first_template == (generated / "decision_intake_template.json").read_bytes()
    ledger = json.loads(first_ledger)
    assert ledger["summary"]["unresolved_required_count"] == 0
    assert ledger["summary"]["follow_up_required_count"] == 1


def test_malformed_intake_and_inputs_exit_1_without_outputs(tmp_path):
    generated, _, _, _ = make_inputs(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    result = run_cli(generated, "--intake", str(bad))
    assert result.returncode == 1
    assert not (generated / "decision_ledger.json").exists()

    for filename in ["contest_requirements.json", "requirement_capability_match.json", "capability_registry.json"]:
        generated, _, _, _ = make_inputs(tmp_path / filename)
        (generated / filename).write_text("{bad", encoding="utf-8")
        result = run_cli(generated)
        assert result.returncode == 1
        assert not (generated / "decision_ledger.json").exists()


def test_stale_conflicting_and_source_digest_warning_exit_2(tmp_path):
    generated, requirements, matches, capabilities = make_inputs(tmp_path)
    stale_path = tmp_path / "stale.json"
    write_json(stale_path, confirmed_intake(requirements, matches, capabilities, stale=True))
    stale = run_cli(generated, "--intake", str(stale_path))
    assert stale.returncode == 2
    assert json.loads((generated / "decision_ledger.json").read_text(encoding="utf-8"))["summary"]["stale"] == 1

    generated, requirements, matches, capabilities = make_inputs(tmp_path / "conflict")
    conflict = confirmed_intake(requirements, matches, capabilities)
    second = json.loads(json.dumps(conflict["decisions"][0]))
    second["decision_id"] = "dec.solver.task_solution.r002"
    conflict["decisions"].append(second)
    conflict_path = tmp_path / "conflict.json"
    write_json(conflict_path, conflict)
    result = run_cli(generated, "--intake", str(conflict_path))
    assert result.returncode == 2
    ledger = json.loads((generated / "decision_ledger.json").read_text(encoding="utf-8"))
    assert ledger["summary"]["conflicting"] == 1

    generated, requirements, matches, capabilities = make_inputs(tmp_path / "source")
    warning_path = tmp_path / "source_warning.json"
    write_json(warning_path, confirmed_intake(requirements, matches, capabilities, source_mismatch=True))
    result = run_cli(generated, "--intake", str(warning_path))
    assert result.returncode == 0
    ledger = json.loads((generated / "decision_ledger.json").read_text(encoding="utf-8"))
    assert ledger["warnings"] == ["Decision intake source digest mismatch for contest_requirements."]
