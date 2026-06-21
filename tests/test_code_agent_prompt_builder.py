from __future__ import annotations

import json

from factory.code_agent_prompt_builder import (
    PROMPT_FILENAME,
    build_code_agent_work_package,
    save_code_agent_work_package,
)


def candidates(tasks=None, overrides=None) -> dict:
    return {
        "source_response_path": "generated/ai_problem_analysis_response.md",
        "contest_path": "examples/mock_contest_02",
        "parsed": True,
        "parse_warnings": ["minor warning"],
        "payload": {
            "problem_type_candidates": [{"value": "classification", "confidence": "high"}],
            "input_structure": {"summary": "CSV train/test files"},
            "output_structure": {"required_columns": ["id", "label"]},
            "evaluation_metric_candidates": [{"value": "accuracy", "confidence": "high"}],
            "rule_risks": [{"item": "external_api", "risk": "forbidden"}],
            "usage_candidates": {"external_api_allowed": {"value": False}},
            "required_harness_modules": [{"name": "loader"}],
            "solver_candidates": [{"name": "local_baseline"}],
            "human_decisions": [{"decision": "Use local baseline only"}],
            "contest_spec_updates": [{"path": "problem.task_type", "value": "classification"}],
            "harness_blueprint_updates": [{"path": "solver_requirements", "value": "baseline"}],
            "code_agent_tasks": tasks if tasks is not None else [
                {
                    "title": "Add loader guard",
                    "priority": "P1",
                    "files": ["templates/base_harness/src/loader.py", "tests/test_harness_generator.py"],
                    "acceptance_criteria": ["pytest -q passes", "loader rejects missing text column"],
                }
            ],
        },
        "accepted_override_candidates": overrides if overrides is not None else [
            {"path": "problem.task_type", "value": "classification", "confidence": "high"}
        ],
        "rejected_override_candidates": [{"path": "rules.internet_allowed", "reason": "low confidence"}],
        "conflicting_override_candidates": [{"path": "output.value_constraints", "reason": "duplicate candidate path"}],
        "already_confirmed_candidates": [{"path": "rules.external_api_allowed", "value": False}],
    }


def contest_spec() -> dict:
    return {
        "contest": {"name": "한국어 Mock 02", "source_path": "examples/mock_contest_02"},
        "problem": {"task_type": "classification", "evaluation_metric": "accuracy"},
        "files": {"train": {"path": "train.csv", "columns": ["id", "text", "label"], "row_count": 2}},
        "schema": {"common_columns": ["id", "text"], "train_only_columns": ["label"]},
        "rules": {"external_api_allowed": False, "internet_allowed": False},
        "output": {"required_columns": ["id", "label"], "id_column": "id", "target_column": "label"},
        "unknowns": [{"item": "rules.pretrained_model_allowed"}],
        "human_decision_values": {"final_solver_policy": "local_baseline_only"},
        "decision_overrides": {"applied": [{"item": "problem.evaluation_metric", "value": "accuracy"}]},
        "source_documents": {"description_present": True},
    }


def write_artifacts(tmp_path, *, tasks=None, include_review=True, malformed_candidates=False):
    output = tmp_path / "generated"
    output.mkdir()
    analysis = output / "ai_analysis_candidates.json"
    if malformed_candidates:
        analysis.write_text("{bad", encoding="utf-8")
    else:
        analysis.write_text(json.dumps(candidates(tasks), ensure_ascii=False), encoding="utf-8")
    (output / "contest_spec.json").write_text(json.dumps(contest_spec(), ensure_ascii=False), encoding="utf-8")
    (output / "gap_report.md").write_text("# Gap Report\n\n- pretrained model unknown\n", encoding="utf-8")
    (output / "harness_blueprint.md").write_text("# Harness Blueprint\n\n- local baseline\n", encoding="utf-8")
    (output / "code_agent_task_plan.md").write_text("# Code Agent Task Plan\n\n- Add loader guard\n", encoding="utf-8")
    if include_review:
        (output / "ai_analysis_review.md").write_text("# AI Analysis Review\n\n- accepted candidate\n", encoding="utf-8")
    return output, analysis


def test_context_json_contains_required_structure(tmp_path):
    output, analysis = write_artifacts(tmp_path)

    context, _ = build_code_agent_work_package(
        contest_path="examples/mock_contest_02",
        analysis_candidates_path=analysis,
        output_dir=output,
    )

    assert context["version"] == "v0.8"
    assert context["contest_path"] == "examples/mock_contest_02"
    assert context["source_files"]["contest_spec"].endswith("contest_spec.json")
    assert context["project_state"]["offline_only"] is True
    assert context["project_state"]["automatic_code_execution"] is False
    assert context["project_state"]["automatic_source_modification"] is False
    assert context["contest_spec_summary"]["problem"]["task_type"] == "classification"
    assert context["analysis_summary"]["accepted_override_candidates"]
    assert context["analysis_summary"]["rejected_override_candidates"]
    assert context["analysis_summary"]["conflicting_override_candidates"]
    assert context["analysis_summary"]["already_confirmed_candidates"]
    assert context["analysis_summary"]["human_decisions"]
    assert context["code_agent_tasks"][0]["title"] == "Add loader guard"
    assert "OpenAI API runtime 호출 금지" in context["constraints"]
    assert "pytest -q" in context["verification_commands"]
    assert "pytest 결과" in context["completion_report_sections"]


def test_prompt_contains_required_sections_and_artifacts(tmp_path):
    output, analysis = write_artifacts(tmp_path)

    _, prompt = build_code_agent_work_package(
        contest_path="examples/mock_contest_02",
        analysis_candidates_path=analysis,
        output_dir=output,
    )

    for section in [
        "# Code Agent Implementation Prompt",
        "## Role",
        "## Repository",
        "## Current Project State",
        "## Contest Context",
        "## Current ContestSpec Summary",
        "## Gap Report",
        "## Harness Blueprint",
        "## AI Analysis Review",
        "## Human Decisions",
        "## Override Candidate Status",
        "## Implementation Tasks",
        "## Files Allowed to Change",
        "## Files That Must Not Be Modified",
        "## Implementation Constraints",
        "## Required Verification",
        "## Completion Report Format",
    ]:
        assert section in prompt
    assert "classification" in prompt
    assert "pretrained model unknown" in prompt
    assert "local baseline" in prompt
    assert "accepted candidate" in prompt
    assert "Add loader guard" in prompt
    assert "pytest -q passes" in prompt
    assert "python factory/run_factory.py --contest examples/mock_contest_01" in prompt
    assert "generated/와 runs/가 커밋 대상이 아닌지 확인" in prompt
    assert "{{" not in prompt


def test_task_without_candidates_does_not_invent_work(tmp_path):
    output, analysis = write_artifacts(tmp_path, tasks=[])

    context, prompt = build_code_agent_work_package(
        contest_path="examples/mock_contest_02",
        analysis_candidates_path=analysis,
        output_dir=output,
    )

    assert context["code_agent_tasks"] == []
    assert "- 구현 작업 후보 없음" in prompt
    assert "Task 1" not in prompt


def test_unsafe_task_paths_are_excluded_and_warned(tmp_path):
    tasks = [
        {
            "title": "Unsafe path filtering",
            "priority": "P1",
            "files": [
                "/tmp/outside.py",
                "../outside.py",
                "generated/final_harness/run.py",
                "runs/run_001/run_log.json",
                ".git/config",
                ".venv/pyvenv.cfg",
                "configs/.env",
                "secrets/token.txt",
                "templates/base_harness/src/loader.py",
            ],
            "acceptance_criteria": ["unsafe paths are warned"],
        }
    ]
    output, analysis = write_artifacts(tmp_path, tasks=tasks)

    context, prompt = build_code_agent_work_package(
        contest_path="examples/mock_contest_02",
        analysis_candidates_path=analysis,
        output_dir=output,
    )

    assert context["allowed_files"] == ["templates/base_harness/src/loader.py"]
    warned_paths = {item["path"] for item in context["unsafe_task_path_warnings"]}
    assert "/tmp/outside.py" in warned_paths
    assert "../outside.py" in warned_paths
    assert "generated/final_harness/run.py" in warned_paths
    assert "runs/run_001/run_log.json" in warned_paths
    assert ".git/config" in warned_paths
    assert ".venv/pyvenv.cfg" in warned_paths
    assert "configs/.env" in warned_paths
    assert "secrets/token.txt" in warned_paths
    assert "/tmp/outside.py" not in prompt
    assert "- templates/base_harness/src/loader.py" in prompt


def test_optional_ai_review_can_be_missing(tmp_path):
    output, analysis = write_artifacts(tmp_path, include_review=False)

    context, prompt = build_code_agent_work_package(
        contest_path="examples/mock_contest_02",
        analysis_candidates_path=analysis,
        output_dir=output,
    )

    assert context["source_files"]["ai_analysis_review"] == ""
    assert "## AI Analysis Review" in prompt


def test_save_outputs_use_utf8_json_and_fixed_names(tmp_path):
    output, analysis = write_artifacts(tmp_path)

    paths = save_code_agent_work_package(
        contest_path="examples/mock_contest_02",
        analysis_candidates_path=analysis,
        output_dir=output,
    )

    context_text = paths["context_json"].read_text(encoding="utf-8")
    assert paths["implementation_prompt"].name == PROMPT_FILENAME
    assert paths["context_json"].name == "code_agent_context.json"
    assert "\n  " in context_text
    assert "한국어 Mock 02" in context_text
    assert "\\ud55c\\uad6d" not in context_text
    assert json.loads(context_text)["version"] == "v0.8"


def test_builder_does_not_modify_real_contest_overrides(tmp_path):
    output, analysis = write_artifacts(tmp_path)
    overrides_path = "examples/mock_contest_02/contest_overrides.yaml"
    before = open(overrides_path, encoding="utf-8").read()

    save_code_agent_work_package(
        contest_path="examples/mock_contest_02",
        analysis_candidates_path=analysis,
        output_dir=output,
    )

    after = open(overrides_path, encoding="utf-8").read()
    assert after == before


def test_builder_does_not_modify_source_artifacts(tmp_path):
    output, analysis = write_artifacts(tmp_path)
    inputs = [
        analysis,
        output / "contest_spec.json",
        output / "gap_report.md",
        output / "harness_blueprint.md",
        output / "ai_analysis_review.md",
        output / "code_agent_task_plan.md",
    ]
    before = {path: path.read_text(encoding="utf-8") for path in inputs}

    save_code_agent_work_package(
        contest_path="examples/mock_contest_02",
        analysis_candidates_path=analysis,
        output_dir=output,
    )

    assert {path: path.read_text(encoding="utf-8") for path in inputs} == before
