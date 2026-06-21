from __future__ import annotations

import json
import subprocess
import sys


def response_for(payload: dict) -> str:
    return (
        "## Machine-readable Analysis Payload\n\n"
        "```json\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "```\n"
    )


def payload() -> dict:
    return {
        "candidate_overrides": [
            {"path": "problem.task_type", "value": "classification", "confidence": "high", "evidence": "schema"}
        ],
        "code_agent_tasks": [
            {
                "title": "Review loader",
                "priority": "P1",
                "files": ["templates/base_harness/src/loader.py"],
                "acceptance_criteria": ["pytest passes"],
            }
        ],
        "human_decisions": [],
    }


def test_cli_success_generates_outputs(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    response = tmp_path / "response.md"
    response.write_text(response_for(payload()), encoding="utf-8")
    output = tmp_path / "generated"

    result = subprocess.run(
        [
            sys.executable,
            "factory/run_ai_analysis_review.py",
            "--contest",
            str(contest),
            "--analysis-response",
            str(response),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "[OK] AI analysis review artifacts generated" in result.stdout
    assert (output / "ai_analysis_candidates.json").exists()
    assert (output / "ai_analysis_review.md").exists()
    assert (output / "contest_overrides.proposed.yaml").exists()
    assert (output / "code_agent_task_plan.md").exists()


def test_cli_invalid_response_returns_non_zero(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    response = tmp_path / "response.md"
    response.write_text("No machine payload", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "factory/run_ai_analysis_review.py",
            "--contest",
            str(contest),
            "--analysis-response",
            str(response),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Missing required heading" in result.stderr
