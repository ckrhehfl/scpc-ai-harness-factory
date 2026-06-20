from pathlib import Path
from factory.spec_builder import build_contest_spec
from factory.harness_generator import generate_harness


def test_generate_harness(tmp_path):
    spec = build_contest_spec("examples/mock_contest_01")
    out = tmp_path / "final_harness"
    generate_harness(spec, output_dir=out)
    assert (out / "run.py").exists()
    assert (out / "configs" / "default.json").exists()
    assert (out / "src" / "solver.py").exists()
