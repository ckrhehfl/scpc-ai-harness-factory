from __future__ import annotations

import json
import subprocess
import sys


def candidates() -> dict:
    return {
        "parsed": True,
        "parse_warnings": [],
        "payload": {
            "human_decisions": [{"decision": "local only"}],
            "code_agent_tasks": [
                {
                    "title": "Review verifier",
                    "priority": "P1",
                    "files": ["templates/base_harness/src/verifier.py"],
                    "acceptance_criteria": ["pytest passes"],
                }
            ],
        },
        "accepted_override_candidates": [],
        "rejected_override_candidates": [],
        "conflicting_override_candidates": [],
        "already_confirmed_candidates": [],
    }


def contest_spec() -> dict:
    return {
        "contest": {"name": "Mock", "source_path": "examples/mock_contest_02"},
        "problem": {"task_type": "classification"},
        "files": {},
        "schema": {},
        "rules": {"external_api_allowed": False},
        "output": {"required_columns": ["id", "label"]},
        "unknowns": [],
        "human_decision_values": {},
        "decision_overrides": {"applied": []},
    }


def write_required_artifacts(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    output = tmp_path / "generated"
    output.mkdir()
    analysis = output / "ai_analysis_candidates.json"
    analysis.write_text(json.dumps(candidates(), ensure_ascii=False), encoding="utf-8")
    (output / "contest_spec.json").write_text(json.dumps(contest_spec(), ensure_ascii=False), encoding="utf-8")
    (output / "gap_report.md").write_text("# Gap Report\n", encoding="utf-8")
    (output / "harness_blueprint.md").write_text("# Harness Blueprint\n", encoding="utf-8")
    (output / "ai_analysis_review.md").write_text("# AI Analysis Review\n", encoding="utf-8")
    (output / "code_agent_task_plan.md").write_text("# Code Agent Task Plan\n", encoding="utf-8")
    return contest, output, analysis


def run_cli(contest, analysis, output):
    return subprocess.run(
        [
            sys.executable,
            "factory/run_code_agent_prompt.py",
            "--contest",
            str(contest),
            "--analysis-candidates",
            str(analysis),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_success_generates_two_outputs(tmp_path):
    contest, output, analysis = write_required_artifacts(tmp_path)

    result = run_cli(contest, analysis, output)

    assert result.returncode == 0
    assert "[OK] Code agent work package generated" in result.stdout
    assert (output / "code_agent_implementation_prompt.md").exists()
    assert (output / "code_agent_context.json").exists()
    prompt = (output / "code_agent_implementation_prompt.md").read_text(encoding="utf-8")
    assert "Code Agent Implementation Prompt" in prompt
    assert "Current Project State" in prompt
    assert "Current ContestSpec Summary" in prompt
    assert "Gap Report" in prompt
    assert "Harness Blueprint" in prompt
    assert "Implementation Tasks" in prompt
    assert "Implementation Constraints" in prompt
    assert "Required Verification" in prompt
    assert "Completion Report Format" in prompt


def test_cli_missing_analysis_candidates_returns_non_zero_without_prompt(tmp_path):
    contest, output, analysis = write_required_artifacts(tmp_path)
    analysis.unlink()

    result = run_cli(contest, analysis, output)

    assert result.returncode != 0
    assert "Required analysis candidates JSON not found" in result.stderr
    assert not (output / "code_agent_implementation_prompt.md").exists()
    assert not (output / "code_agent_context.json").exists()


def test_cli_malformed_json_returns_non_zero_without_prompt(tmp_path):
    contest, output, analysis = write_required_artifacts(tmp_path)
    analysis.write_text("{bad", encoding="utf-8")

    result = run_cli(contest, analysis, output)

    assert result.returncode != 0
    assert "Malformed analysis candidates JSON" in result.stderr
    assert not (output / "code_agent_implementation_prompt.md").exists()
    assert not (output / "code_agent_context.json").exists()


def test_cli_missing_required_factory_artifact_returns_non_zero(tmp_path):
    contest, output, analysis = write_required_artifacts(tmp_path)
    (output / "harness_blueprint.md").unlink()

    result = run_cli(contest, analysis, output)

    assert result.returncode != 0
    assert "Required factory artifact not found" in result.stderr
    assert not (output / "code_agent_implementation_prompt.md").exists()
    assert not (output / "code_agent_context.json").exists()


def test_cli_does_not_modify_real_contest_overrides(tmp_path):
    contest, output, analysis = write_required_artifacts(tmp_path)
    overrides_path = "examples/mock_contest_02/contest_overrides.yaml"
    before = open(overrides_path, encoding="utf-8").read()

    result = run_cli(contest, analysis, output)

    assert result.returncode == 0
    after = open(overrides_path, encoding="utf-8").read()
    assert after == before
