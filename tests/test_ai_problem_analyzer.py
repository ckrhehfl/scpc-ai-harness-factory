from __future__ import annotations

from factory.ai_problem_analyzer import build_problem_analysis_prompt, save_ai_problem_analysis_prompt
from factory.blueprint_generator import build_harness_blueprint
from factory.gap_analyzer import analyze_gaps
from factory.input_scanner import scan_contest_inputs
from factory.spec_builder import build_contest_spec


def test_problem_analysis_prompt_contains_required_context_and_requests(tmp_path):
    scan = scan_contest_inputs("examples/mock_contest_02")
    spec = build_contest_spec("examples/mock_contest_02")
    gap_report = analyze_gaps(spec)
    blueprint = build_harness_blueprint(spec, gap_report, templates_dir=tmp_path)

    prompt = build_problem_analysis_prompt(scan, spec, gap_report, blueprint)

    assert "# Source Documents" in prompt
    assert "Mock Contest 02" in prompt
    assert "Allowed labels" in prompt
    assert "# Input Scan Report" in prompt
    assert "train.csv" in prompt
    assert "first_row_preview" in prompt
    assert "Current ContestSpec Summary" in prompt
    assert "Current GapReport Summary" in prompt
    assert "Current HarnessBlueprint Summary" in prompt
    assert "Candidate ContestSpec updates" in prompt
    assert "Candidate HarnessBlueprint updates" in prompt
    assert "Code Agent Task Plan" in prompt
    assert "Do not add runtime LLM API calls" in prompt

    path = save_ai_problem_analysis_prompt(scan, spec, gap_report, blueprint, tmp_path)
    assert path.exists()
    assert "API / external data / internet" in path.read_text(encoding="utf-8")
