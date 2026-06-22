from __future__ import annotations

from pathlib import Path
import copy
import json
import zipfile

from factory.decision_ledger_builder import build_decision_ledger
from factory.decision_model import canonical_json_digest
from factory.human_approval_builder import build_human_approval_summary
from factory.requirement_model import build_match_summary, build_requirements_artifact
from factory.submission_handoff_builder import (
    build_freeze_confirmation_template,
    build_submission_handoff,
    save_submission_handoff_outputs,
)


def req():
    return {
        "requirement_id": "req.solver.task_solution",
        "title": "task solution",
        "origin": "contest_spec",
        "domain": "solver",
        "requirement_type": "capability",
        "priority": "must",
        "provenance_status": "observed",
        "applicability": "active",
        "risk_level": "green",
        "required_tokens": ["solver.classification.predict"],
        "parameters": {},
        "source_refs": [{"artifact": "contest_spec.json", "path": "problem"}],
        "evidence_ids": [],
        "notes": [],
    }


def match():
    return {
        "requirement_id": "req.solver.task_solution",
        "match_status": "satisfied",
        "required_tokens": ["solver.classification.predict"],
        "token_matches": [
            {
                "token": "solver.classification.predict",
                "eligible_capability_ids": ["cap.solver.classification"],
                "limited_capability_ids": [],
                "ineligible_capability_ids": [],
                "blocked_capability_ids": [],
            }
        ],
        "matched_capability_ids": ["cap.solver.classification"],
        "dependency_capability_ids": [],
        "missing_tokens": [],
        "blocked_by": [],
        "notes": [],
    }


def cap():
    return {
        "capability_id": "cap.solver.classification",
        "matching_eligibility": "eligible",
        "verification_status": "verified",
        "provides": ["solver.classification.predict"],
        "dependencies": [],
        "risk_gates": [],
    }


def base_artifacts():
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
        "summary": build_match_summary(requirements["requirements"], [match_record]),
        "matches": [match_record],
        "unmatched_tokens": [],
        "warnings": [],
    }
    capabilities = {"schema_version": "v0.10A", "artifact_type": "capability_registry", "capabilities": [cap()]}
    ledger = build_decision_ledger(requirements, matches, capabilities, None)
    return requirements, matches, capabilities, ledger


def validation_report(submission: Path, *, passed=True):
    return {
        "passed": passed,
        "error_count": 0 if passed else 1,
        "warning_count": 0,
        "submission_path": str(submission),
        "checks": [
            {"name": "submission_file_exists", "passed": True, "severity": "error", "message": str(submission), "details": {"path": str(submission)}},
            {
                "name": "required_columns_present",
                "passed": True,
                "severity": "error",
                "message": "columns",
                "details": {"submission_columns": ["id", "label"], "sample_submission_csv_path": "/private/sample_submission.csv"},
            },
            {
                "name": "row_count_matches_test",
                "passed": passed,
                "severity": "error",
                "message": "/private/test.csv",
                "details": {"submission_row_count": 2, "test_csv_path": "/private/test.csv"},
            },
        ],
    }


def approved_summary(requirements, matches, ledger, capabilities, report):
    reviewable = build_human_approval_summary(requirements, matches, ledger, capabilities, validation_report=report)
    approval = {
        "schema_version": "v0.11B",
        "artifact_type": "human_approval_intake",
        "source_digests": copy.deepcopy(reviewable["source_digests"]),
        "readiness_digest": reviewable["readiness_digest"],
        "approvals": [
            {
                "approval_id": "approval.local_submission_candidate.r001",
                "scope": "local_submission_candidate",
                "expected_readiness_digest": reviewable["readiness_digest"],
                "actor": "human",
                "approval_status": "approved",
                "rationale": "Reviewed the exact local candidate.",
                "conditions": [],
                "supersedes": None,
                "notes": [],
            }
        ],
        "notes": [],
    }
    return build_human_approval_summary(requirements, matches, ledger, capabilities, validation_report=report, approval_intake=approval)


def fixture(tmp_path: Path):
    submission = tmp_path / "submission.csv"
    submission.write_bytes(b"id,label\n1,A\n2,B\n")
    requirements, matches, capabilities, ledger = base_artifacts()
    report = validation_report(submission)
    summary = approved_summary(requirements, matches, ledger, capabilities, report)
    return submission, report, summary, ledger, requirements, matches, capabilities


def build(tmp_path: Path, *, freeze=None, mutate=None):
    submission, report, summary, ledger, requirements, matches, capabilities = fixture(tmp_path)
    if mutate:
        mutate(submission, report, summary, ledger, requirements, matches, capabilities)
    return build_submission_handoff(
        submission_path=submission,
        validation_report=report,
        human_approval_summary=summary,
        decision_ledger=ledger,
        requirements=requirements,
        matches=matches,
        capabilities=capabilities,
        freeze_confirmation=freeze,
    )


def freeze(candidate_digest: str, *, status="confirmed", second_leaf=False, stale=False):
    entry = {
        "confirmation_id": "freeze.local_submission_candidate.r001",
        "scope": "local_submission_candidate",
        "expected_candidate_digest": "sha256:" + "9" * 64 if stale else candidate_digest,
        "actor": "human",
        "confirmation_status": status,
        "rationale": "" if status == "pending" else "I verified the exact handoff candidate digest for manual submission.",
        "supersedes": None,
        "notes": [],
    }
    confirmations = [entry]
    if second_leaf:
        other = copy.deepcopy(entry)
        other["confirmation_id"] = "freeze.local_submission_candidate.r002"
        confirmations.append(other)
    return {
        "schema_version": "v0.12",
        "artifact_type": "freeze_confirmation_intake",
        "scope": "local_submission_candidate",
        "candidate_digest": candidate_digest,
        "confirmations": confirmations,
        "notes": [],
    }


def test_preflight_blocks_approval_and_source_and_validation_failures(tmp_path: Path):
    manifest, package = build(tmp_path, mutate=lambda s, r, summary, *_: summary["human_approval"].update({"approval_granted": False}))
    assert manifest["status"] == "blocked"
    assert package == {}

    manifest, _ = build(tmp_path, mutate=lambda s, r, summary, *_: summary["source_digests"].update({"contest_requirements": "sha256:" + "8" * 64}))
    assert manifest["status"] == "blocked"
    assert "handoff.sources.requirements_digest_current" in {c["check_id"] for c in manifest["preflight"]["checks"] if c["status"] == "fail"}

    manifest, _ = build(tmp_path, mutate=lambda s, r, *_: r.update({"passed": False, "error_count": 1}))
    assert manifest["status"] == "blocked"


def test_submission_safety_path_and_snapshot_blockers(tmp_path: Path):
    def case(name: str) -> Path:
        path = tmp_path / name
        path.mkdir()
        return path

    manifest, _ = build(case("missing"), mutate=lambda s, r, *_: s.unlink())
    assert manifest["status"] == "blocked"

    def symlink_submission(submission, report, *_):
        target = submission.parent / "target.csv"
        target.write_bytes(submission.read_bytes())
        submission.unlink()
        submission.symlink_to(target)

    manifest, _ = build(case("symlink"), mutate=symlink_submission)
    assert manifest["status"] == "blocked"

    def directory_submission(submission, report, *_):
        submission.unlink()
        submission.mkdir()

    manifest, _ = build(case("directory"), mutate=directory_submission)
    assert manifest["status"] == "blocked"

    manifest, _ = build(case("malformed"), mutate=lambda s, r, *_: s.write_bytes(b"\xff\xfe"))
    assert manifest["status"] == "blocked"

    manifest, _ = build(case("path"), mutate=lambda s, r, *_: r.update({"submission_path": str(s.parent / "other.csv")}))
    assert manifest["status"] == "blocked"
    assert "handoff.submission.report_path_matches" in {c["check_id"] for c in manifest["preflight"]["checks"] if c["status"] == "fail"}

    def columns_mismatch(submission, report, *_):
        report["checks"][1]["details"]["submission_columns"] = ["id", "wrong"]

    manifest, _ = build(case("columns"), mutate=columns_mismatch)
    assert manifest["status"] == "blocked"

    def row_mismatch(submission, report, *_):
        report["checks"][2]["details"]["submission_row_count"] = 3

    manifest, _ = build(case("rows"), mutate=row_mismatch)
    assert manifest["status"] == "blocked"


def test_preflight_pass_without_confirmation_prepared_and_template_r001(tmp_path: Path):
    manifest, package = build(tmp_path)
    assert manifest["status"] == "prepared"
    assert manifest["candidate"]["candidate_digest"].startswith("sha256:")
    assert package["submission/submission.csv"] == b"id,label\n1,A\n2,B\n"
    template = build_freeze_confirmation_template(manifest)
    assert template["confirmations"][0]["confirmation_id"] == "freeze.local_submission_candidate.r001"
    assert template["confirmations"][0]["confirmation_status"] == "pending"


def test_confirmed_rejected_stale_conflicting_and_candidate_stability(tmp_path: Path):
    prepared, _ = build(tmp_path)
    digest = prepared["candidate"]["candidate_digest"]

    frozen, _ = build(tmp_path, freeze=freeze(digest))
    assert frozen["status"] == "frozen"
    assert frozen["candidate"]["candidate_digest"] == digest

    rejected, _ = build(tmp_path, freeze=freeze(digest, status="rejected"))
    assert rejected["status"] == "rejected"
    assert rejected["candidate"]["candidate_digest"] == digest

    stale, _ = build(tmp_path, freeze=freeze(digest, stale=True))
    assert stale["status"] == "stale"

    conflicting, _ = build(tmp_path, freeze=freeze(digest, second_leaf=True))
    assert conflicting["status"] == "conflicting"

    changed, _ = build(tmp_path, mutate=lambda s, *_: s.write_bytes(b"id,label\n1,A\n2,C\n"))
    assert changed["candidate"]["candidate_digest"] != digest


def test_packaged_json_change_changes_candidate_digest_and_raw_validation_is_sanitized(tmp_path: Path):
    manifest, package = build(tmp_path)
    digest = manifest["candidate"]["candidate_digest"]
    changed, _ = build(tmp_path, mutate=lambda s, r, summary, ledger, requirements, *_: requirements["warnings"].append("new warning"))
    assert changed["candidate"]["candidate_digest"] != digest

    evidence = json.loads(package["evidence/validation_evidence.json"].decode("utf-8"))
    payload = json.dumps(evidence, sort_keys=True)
    assert "/private" not in payload
    assert "message" not in payload
    assert "details" not in payload


def test_save_outputs_removes_stale_package_on_blocked_and_zip_is_deterministic(tmp_path: Path):
    output = tmp_path / "generated"
    manifest, package = build(tmp_path)
    template = build_freeze_confirmation_template(manifest)
    first_paths = save_submission_handoff_outputs(manifest, template, package, output)
    first_zip = first_paths["package_zip"].read_bytes()
    second_paths = save_submission_handoff_outputs(manifest, template, package, output)
    assert second_paths["package_zip"].read_bytes() == first_zip

    with zipfile.ZipFile(second_paths["package_zip"]) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == sorted(package)
        assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
        assert all((info.external_attr >> 16) & 0o170000 == 0o100000 for info in infos)
        assert all(info.extra == b"" for info in infos)
        assert archive.comment == b""
        assert not any(info.filename.endswith("/") for info in infos)
        for entry in manifest["candidate"]["entries"]:
            assert canonical_json_digest(manifest) != entry["sha256"]
            assert archive.read(entry["package_path"])

    blocked, blocked_package = build(tmp_path, mutate=lambda s, r, summary, *_: summary["overall_gate"].update({"status": "blocked"}))
    blocked_template = build_freeze_confirmation_template(blocked)
    save_submission_handoff_outputs(blocked, blocked_template, blocked_package, output)
    assert not (output / "submission_handoff_package").exists()
    assert not (output / "submission_handoff_package.zip").exists()
