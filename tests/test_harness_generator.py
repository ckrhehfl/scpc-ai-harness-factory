from pathlib import Path
import csv
import subprocess
import sys

from factory.spec_builder import build_contest_spec
from factory.harness_generator import generate_harness


def test_generate_harness(tmp_path):
    spec = build_contest_spec("examples/mock_contest_01")
    out = tmp_path / "final_harness"
    generate_harness(spec, output_dir=out)
    assert (out / "run.py").exists()
    assert (out / "configs" / "default.json").exists()
    assert (out / "src" / "solver.py").exists()


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
    assert "[OK] submission created" in result.stdout
    assert submission_path.exists()

    with submission_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows
    assert list(rows[0].keys()) == ["id", "label"]
    assert [row["id"] for row in rows] == ["201", "202", "203"]
    assert {row["label"] for row in rows} == {"positive"}
