from pathlib import Path
import csv
import json
import subprocess
import sys

from factory.blueprint_generator import build_harness_blueprint
from factory.gap_analyzer import analyze_gaps
from factory.spec_builder import build_contest_spec
from factory.harness_generator import generate_harness


def test_generate_harness(tmp_path):
    spec = build_contest_spec("examples/mock_contest_01")
    blueprint = build_harness_blueprint(spec, analyze_gaps(spec), templates_dir=tmp_path)
    out = tmp_path / "final_harness"
    generate_harness(spec, blueprint=blueprint, output_dir=out)
    assert (out / "run.py").exists()
    assert (out / "configs" / "default.json").exists()
    assert (out / "src" / "solver.py").exists()
    config = json.loads((out / "configs" / "default.json").read_text(encoding="utf-8"))
    assert "harness_blueprint" in config
    assert config["verifier"]["test_csv_path"] == "examples/mock_contest_01/test.csv"
    assert config["verifier"]["sample_submission_csv_path"] == "examples/mock_contest_01/sample_submission.csv"
    assert config["verifier"]["required_columns"] == ["id", "answer"]


def test_generated_harness_runs_for_text_classification(tmp_path):
    spec = build_contest_spec("examples/mock_contest_02")
    out = tmp_path / "final_harness"
    generate_harness(spec, output_dir=out)

    result = subprocess.run(
        [sys.executable, str(out / "run.py")],
        check=True,
        capture_output=True,
        text=True,
    )

    submission_path = out / "outputs" / "submission.csv"
    report_json_path = out / "outputs" / "validation_report.json"
    report_md_path = out / "outputs" / "validation_report.md"
    assert "[OK] submission created" in result.stdout
    assert "[OK] validation report created" in result.stdout
    assert submission_path.exists()
    assert report_json_path.exists()
    assert report_md_path.exists()

    with submission_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    report = json.loads(report_json_path.read_text(encoding="utf-8"))

    assert rows
    assert list(rows[0].keys()) == ["id", "label"]
    assert [row["id"] for row in rows] == ["201", "202", "203"]
    assert {row["label"] for row in rows} == {"positive"}
    assert report["passed"] is True
    allowed_label_check = next(check for check in report["checks"] if check["name"] == "target_values_in_allowed_labels")
    assert allowed_label_check["details"]["allowed_labels"] == ["negative", "positive"]
