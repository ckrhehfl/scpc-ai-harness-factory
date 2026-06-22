from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

from test_submission_handoff_builder import approved_summary, base_artifacts, freeze, validation_report


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "factory" / "run_submission_handoff.py"


def write_fixture(tmp_path: Path):
    submission = tmp_path / "submission.csv"
    submission.write_bytes(b"id,label\n1,A\n2,B\n")
    requirements, matches, capabilities, ledger = base_artifacts()
    report = validation_report(submission)
    summary = approved_summary(requirements, matches, ledger, capabilities, report)
    paths = {
        "submission": submission,
        "validation_report": tmp_path / "validation_report.json",
        "approval_summary": tmp_path / "human_approval_summary.json",
        "decision_ledger": tmp_path / "decision_ledger.json",
        "requirements": tmp_path / "contest_requirements.json",
        "matches": tmp_path / "requirement_capability_match.json",
        "capabilities": tmp_path / "capability_registry.json",
    }
    for key, value in [
        ("validation_report", report),
        ("approval_summary", summary),
        ("decision_ledger", ledger),
        ("requirements", requirements),
        ("matches", matches),
        ("capabilities", capabilities),
    ]:
        paths[key].write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def run_cli(paths: dict[str, Path], output: Path, freeze_confirmation: Path | None = None) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(SCRIPT),
        "--submission",
        str(paths["submission"]),
        "--validation-report",
        str(paths["validation_report"]),
        "--approval-summary",
        str(paths["approval_summary"]),
        "--decision-ledger",
        str(paths["decision_ledger"]),
        "--requirements",
        str(paths["requirements"]),
        "--matches",
        str(paths["matches"]),
        "--capabilities",
        str(paths["capabilities"]),
        "--output",
        str(output),
    ]
    if freeze_confirmation is not None:
        args.extend(["--freeze-confirmation", str(freeze_confirmation)])
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, check=False)


def manifest(output: Path) -> dict:
    return json.loads((output / "submission_handoff_manifest.json").read_text(encoding="utf-8"))


def test_cli_prepared_frozen_rejected_stale_conflicting_and_deterministic(tmp_path: Path):
    paths = write_fixture(tmp_path)
    output = tmp_path / "generated"

    prepared = run_cli(paths, output)
    assert prepared.returncode == 2
    assert "- Handoff status: prepared" in prepared.stdout
    prepared_manifest = manifest(output)
    digest = prepared_manifest["candidate"]["candidate_digest"]
    first_zip = (output / "submission_handoff_package.zip").read_bytes()
    assert str(paths["submission"].resolve()) not in (output / "submission_handoff_manifest.json").read_text(encoding="utf-8")

    rerun = run_cli(paths, output)
    assert rerun.returncode == 2
    assert (output / "submission_handoff_package.zip").read_bytes() == first_zip

    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(freeze(digest), ensure_ascii=False, indent=2), encoding="utf-8")
    frozen = run_cli(paths, output, freeze_path)
    assert frozen.returncode == 0
    assert manifest(output)["status"] == "frozen"
    assert manifest(output)["candidate"]["candidate_digest"] == digest

    freeze_path.write_text(json.dumps(freeze(digest, status="rejected"), ensure_ascii=False, indent=2), encoding="utf-8")
    rejected = run_cli(paths, output, freeze_path)
    assert rejected.returncode == 2
    assert manifest(output)["status"] == "rejected"

    freeze_path.write_text(json.dumps(freeze(digest, stale=True), ensure_ascii=False, indent=2), encoding="utf-8")
    stale = run_cli(paths, output, freeze_path)
    assert stale.returncode == 2
    assert manifest(output)["status"] == "stale"

    freeze_path.write_text(json.dumps(freeze(digest, second_leaf=True), ensure_ascii=False, indent=2), encoding="utf-8")
    conflict = run_cli(paths, output, freeze_path)
    assert conflict.returncode == 2
    assert manifest(output)["status"] == "conflicting"


def test_cli_blocked_exit_2_no_package_and_cleans_stale_package(tmp_path: Path):
    paths = write_fixture(tmp_path)
    output = tmp_path / "generated"
    assert run_cli(paths, output).returncode == 2
    assert (output / "submission_handoff_package.zip").exists()

    summary = json.loads(paths["approval_summary"].read_text(encoding="utf-8"))
    summary["overall_gate"]["status"] = "blocked"
    paths["approval_summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    blocked = run_cli(paths, output)
    assert blocked.returncode == 2
    data = manifest(output)
    assert data["status"] == "blocked"
    assert data["candidate"]["candidate_digest"] is None
    assert not (output / "submission_handoff_package").exists()
    assert not (output / "submission_handoff_package.zip").exists()


def test_cli_malformed_inputs_exit_1_without_output(tmp_path: Path):
    paths = write_fixture(tmp_path)
    output = tmp_path / "generated"
    paths["approval_summary"].write_text("{bad", encoding="utf-8")

    result = run_cli(paths, output)

    assert result.returncode == 1
    assert "[ERROR]" in result.stderr
    assert not output.exists()


def test_cli_missing_submission_is_preflight_blocker_exit_2(tmp_path: Path):
    paths = write_fixture(tmp_path)
    output = tmp_path / "generated"
    paths["submission"].unlink()

    result = run_cli(paths, output)

    assert result.returncode == 2
    assert manifest(output)["status"] == "blocked"
    assert not (output / "submission_handoff_package.zip").exists()
