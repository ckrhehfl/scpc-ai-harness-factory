from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

from factory.evidence_index_builder import build_evidence_index
from factory.input_scanner import scan_contest_inputs
from factory.spec_builder import build_contest_spec
from factory.utils import write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "factory" / "run_requirement_match.py"


def make_artifacts(tmp_path, *, solver_capability=False):
    contest = tmp_path / "contest"
    contest.mkdir()
    (contest / "train.csv").write_text("id,text,label\n1,a,A\n", encoding="utf-8")
    (contest / "test.csv").write_text("id,text\n2,b\n", encoding="utf-8")
    (contest / "sample_submission.csv").write_text("id,label\n2,A\n", encoding="utf-8")
    generated = tmp_path / "generated"
    scan = scan_contest_inputs(contest)
    spec = build_contest_spec(contest)
    evidence = build_evidence_index(scan, source_artifact="generated/input_scan_report.json")
    registry = registry_fixture(solver_capability=solver_capability)
    write_json(generated / "contest_spec.json", spec)
    write_json(generated / "evidence_index.json", evidence)
    write_json(generated / "capability_registry.json", registry)
    return generated


def registry_fixture(*, solver_capability=False):
    capabilities = [
        cap("cap.generated_harness.csv_loading", ["harness.test_csv.load"]),
        cap("cap.generated_harness.constant_baseline_prediction", ["harness.prediction.rows.emit"], ["cap.generated_harness.csv_loading"]),
        cap("cap.generated_harness.submission_csv_writing", ["submission.csv.write", "submission.columns.order"], ["cap.generated_harness.constant_baseline_prediction"]),
        cap(
            "cap.generated_harness.submission_verification",
            ["submission.schema.verify", "submission.row_count.verify", "submission.id_values.verify", "submission.target_values.verify"],
            ["cap.generated_harness.submission_csv_writing"],
        ),
        cap("cap.generated_harness.validation_report_emission", ["submission.validation_report.write", "submission.validation_report.markdown"], ["cap.generated_harness.submission_verification"]),
    ]
    if solver_capability:
        capabilities.append(cap("cap.solver.classification", ["solver.classification.predict"]))
    return {"schema_version": "v0.10A", "artifact_type": "capability_registry", "capabilities": capabilities}


def cap(capability_id, provides, dependencies=None):
    return {
        "capability_id": capability_id,
        "matching_eligibility": "eligible",
        "provides": provides,
        "dependencies": dependencies or [],
        "risk_gates": [],
    }


def run_cli(generated):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--contest-spec",
            str(generated / "contest_spec.json"),
            "--evidence-index",
            str(generated / "evidence_index.json"),
            "--capabilities",
            str(generated / "capability_registry.json"),
            "--output",
            str(generated),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_success_exit_0_when_all_active_must_requirements_match(tmp_path):
    generated = make_artifacts(tmp_path, solver_capability=True)
    result = run_cli(generated)
    assert result.returncode == 0
    assert "[OK] Requirement contract and capability match generated" in result.stdout
    match = json.loads((generated / "requirement_capability_match.json").read_text(encoding="utf-8"))
    assert match["summary"]["active_must_gap_count"] == 0


def test_cli_mock_solver_gap_exit_2_and_is_deterministic(tmp_path):
    generated = make_artifacts(tmp_path)
    result = run_cli(generated)
    assert result.returncode == 2
    first_req = (generated / "contest_requirements.json").read_bytes()
    first_match = (generated / "requirement_capability_match.json").read_bytes()
    assert str(tmp_path) not in first_req.decode("utf-8")
    assert str(tmp_path) not in first_match.decode("utf-8")
    second = run_cli(generated)
    assert second.returncode == 2
    assert first_req == (generated / "contest_requirements.json").read_bytes()
    assert first_match == (generated / "requirement_capability_match.json").read_bytes()
    match = json.loads(first_match)
    assert {item["requirement_id"]: item for item in match["matches"]}["req.solver.task_solution"]["match_status"] == "unmet"


def test_cli_malformed_inputs_exit_1_without_output(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    bad = generated / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    registry = generated / "capability_registry.json"
    write_json(registry, registry_fixture())
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--contest-spec",
            str(bad),
            "--evidence-index",
            str(bad),
            "--capabilities",
            str(registry),
            "--output",
            str(generated / "out"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "[ERROR]" in result.stderr
    assert not (generated / "out").exists()


def test_cli_malformed_capability_registry_exits_1(tmp_path):
    generated = make_artifacts(tmp_path)
    (generated / "capability_registry.json").write_text(
        json.dumps({"schema_version": "v0.10A", "artifact_type": "bad", "capabilities": []}),
        encoding="utf-8",
    )
    result = run_cli(generated)
    assert result.returncode == 1
    assert "[ERROR]" in result.stderr


def test_cli_malformed_coverage_exits_1_without_output(tmp_path):
    generated = make_artifacts(tmp_path)
    bad_coverage = generated / "bad_coverage.json"
    bad_coverage.write_text(json.dumps({"schema_version": "v0.9B", "artifact_type": "contest_package_coverage"}), encoding="utf-8")
    out = generated / "out"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--contest-spec",
            str(generated / "contest_spec.json"),
            "--evidence-index",
            str(generated / "evidence_index.json"),
            "--capabilities",
            str(generated / "capability_registry.json"),
            "--coverage",
            str(bad_coverage),
            "--output",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "[ERROR]" in result.stderr
    assert not out.exists()


def test_cli_coverage_is_optional_and_input_artifacts_are_not_modified(tmp_path):
    generated = make_artifacts(tmp_path)
    before = {
        name: (generated / name).read_bytes()
        for name in ["contest_spec.json", "evidence_index.json", "capability_registry.json"]
    }
    result = run_cli(generated)
    assert result.returncode == 2
    after = {name: (generated / name).read_bytes() for name in before}
    assert before == after
