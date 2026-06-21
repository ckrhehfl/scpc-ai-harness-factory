from __future__ import annotations

import json

import pytest

from factory.ai_analysis_intake import (
    AnalysisIntakeError,
    build_analysis_candidates,
    build_proposed_overrides,
    extract_machine_payload,
    render_code_agent_task_plan,
    run_analysis_review,
)
from factory.contest_reader import read_simple_yaml


def payload_with(candidate_overrides=None, code_agent_tasks=None, human_decisions=None):
    return {
        "problem_type_candidates": [{"value": "classification", "confidence": "high", "evidence": ["train label"]}],
        "input_structure": {"summary": "CSV files", "files": ["train.csv", "test.csv"]},
        "output_structure": {"summary": "id,label", "required_columns": ["id", "label"]},
        "evaluation_metric_candidates": [{"value": "accuracy", "confidence": "high", "evidence": ["evaluation.md"]}],
        "rule_risks": [{"item": "external_api", "risk": "not allowed", "evidence": "rules.md"}],
        "usage_candidates": {
            "external_api_allowed": {"value": False, "confidence": "high", "evidence": "rules.md"}
        },
        "required_harness_modules": [{"name": "loader", "reason": "CSV"}],
        "solver_candidates": [{"name": "local_baseline", "status": "candidate", "reason": "offline"}],
        "human_decisions": human_decisions if human_decisions is not None else [],
        "contest_spec_updates": [],
        "harness_blueprint_updates": [],
        "candidate_overrides": candidate_overrides if candidate_overrides is not None else [],
        "code_agent_tasks": code_agent_tasks if code_agent_tasks is not None else [],
    }


def response_for(payload: dict) -> str:
    return (
        "# Human analysis\n\n"
        "Some readable sections.\n\n"
        "## Machine-readable Analysis Payload\n\n"
        "```json\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "```\n"
    )


def write_response(tmp_path, payload: dict):
    path = tmp_path / "response.md"
    path.write_text(response_for(payload), encoding="utf-8")
    return path


def make_contest(tmp_path, overrides: str = ""):
    contest = tmp_path / "contest"
    contest.mkdir()
    if overrides:
        (contest / "contest_overrides.yaml").write_text(overrides, encoding="utf-8")
    return contest


def test_extract_machine_payload_parses_valid_response():
    payload = payload_with(
        candidate_overrides=[
            {"path": "problem.task_type", "value": "classification", "confidence": "high", "evidence": "schema"}
        ]
    )

    parsed = extract_machine_payload(response_for(payload))

    assert parsed["candidate_overrides"][0]["path"] == "problem.task_type"
    assert parsed["code_agent_tasks"] == []
    assert parsed["human_decisions"] == []


def test_missing_heading_fails():
    with pytest.raises(AnalysisIntakeError, match="Missing required heading"):
        extract_machine_payload("```json\n{}\n```")


def test_missing_json_fence_fails():
    with pytest.raises(AnalysisIntakeError, match="Missing json fenced code block"):
        extract_machine_payload("## Machine-readable Analysis Payload\n\n{}")


def test_malformed_json_fails():
    with pytest.raises(AnalysisIntakeError, match="Malformed JSON payload"):
        extract_machine_payload("## Machine-readable Analysis Payload\n\n```json\n{\"bad\":\n```")


def test_missing_required_field_fails():
    payload = payload_with()
    del payload["candidate_overrides"]

    with pytest.raises(AnalysisIntakeError, match="Missing required payload field"):
        extract_machine_payload(response_for(payload))


def test_supported_override_path_is_accepted(tmp_path):
    contest = make_contest(tmp_path)
    response = write_response(
        tmp_path,
        payload_with([
            {"path": "problem.task_type", "value": "classification", "confidence": "high", "evidence": "schema"}
        ]),
    )

    candidates = build_analysis_candidates(response_path=response, contest_path=contest)

    assert [item["path"] for item in candidates["accepted_override_candidates"]] == ["problem.task_type"]
    assert candidates["rejected_override_candidates"] == []


def test_unsupported_override_path_is_rejected(tmp_path):
    contest = make_contest(tmp_path)
    response = write_response(
        tmp_path,
        payload_with([
            {"path": "problem.unsupported", "value": "x", "confidence": "high", "evidence": "schema"}
        ]),
    )

    candidates = build_analysis_candidates(response_path=response, contest_path=contest)

    assert candidates["accepted_override_candidates"] == []
    assert candidates["rejected_override_candidates"][0]["reason"] == "unsupported override path"


def test_low_confidence_candidate_is_excluded(tmp_path):
    contest = make_contest(tmp_path)
    response = write_response(
        tmp_path,
        payload_with([
            {"path": "problem.task_type", "value": "classification", "confidence": "low", "evidence": "schema"}
        ]),
    )

    candidates = build_analysis_candidates(response_path=response, contest_path=contest)

    assert candidates["accepted_override_candidates"] == []
    assert candidates["rejected_override_candidates"][0]["reason"] == "low or unknown confidence"


def test_unknown_value_is_excluded(tmp_path):
    contest = make_contest(tmp_path)
    response = write_response(
        tmp_path,
        payload_with([
            {"path": "rules.pretrained_model_allowed", "value": "unknown", "confidence": "high", "evidence": "rules"}
        ]),
    )

    candidates = build_analysis_candidates(response_path=response, contest_path=contest)

    assert candidates["accepted_override_candidates"] == []
    assert candidates["rejected_override_candidates"][0]["reason"] == "empty or unknown value"


def test_duplicate_path_is_conflict_and_excluded(tmp_path):
    contest = make_contest(tmp_path)
    response = write_response(
        tmp_path,
        payload_with([
            {"path": "problem.task_type", "value": "classification", "confidence": "high", "evidence": "schema"},
            {"path": "problem.task_type", "value": "text_qa", "confidence": "medium", "evidence": "description"},
        ]),
    )

    candidates = build_analysis_candidates(response_path=response, contest_path=contest)

    assert candidates["accepted_override_candidates"] == []
    assert len(candidates["conflicting_override_candidates"]) == 2
    assert {item["reason"] for item in candidates["conflicting_override_candidates"]} == {"duplicate candidate path"}


def test_existing_contest_override_conflict_excludes_proposed(tmp_path):
    contest = make_contest(tmp_path, "problem:\n  task_type: classification\n")
    response = write_response(
        tmp_path,
        payload_with([
            {"path": "problem.task_type", "value": "text_qa", "confidence": "high", "evidence": "description"}
        ]),
    )

    candidates = build_analysis_candidates(response_path=response, contest_path=contest)

    assert candidates["accepted_override_candidates"] == []
    assert candidates["conflicting_override_candidates"][0]["existing_value"] == "classification"


def test_existing_contest_override_same_value_is_already_confirmed(tmp_path):
    contest = make_contest(tmp_path, "problem:\n  task_type: classification\n")
    response = write_response(
        tmp_path,
        payload_with([
            {"path": "problem.task_type", "value": "classification", "confidence": "high", "evidence": "schema"}
        ]),
    )

    candidates = build_analysis_candidates(response_path=response, contest_path=contest)

    assert candidates["accepted_override_candidates"] == []
    assert candidates["already_confirmed_candidates"][0]["path"] == "problem.task_type"


def test_real_contest_overrides_file_is_not_modified(tmp_path):
    overrides_path = "examples/mock_contest_02/contest_overrides.yaml"
    before = open(overrides_path, encoding="utf-8").read()
    response = write_response(
        tmp_path,
        payload_with([
            {"path": "rules.external_api_allowed", "value": True, "confidence": "high", "evidence": "ai"}
        ]),
    )

    run_analysis_review(contest_path="examples/mock_contest_02", response_path=response, output_dir=tmp_path / "out")

    after = open(overrides_path, encoding="utf-8").read()
    assert after == before


def test_proposed_yaml_nested_mapping(tmp_path):
    contest = make_contest(tmp_path)
    response = write_response(
        tmp_path,
        payload_with([
            {"path": "problem.task_type", "value": "classification", "confidence": "high", "evidence": "schema"},
            {"path": "rules.external_api_allowed", "value": False, "confidence": "medium", "evidence": "rules"},
        ]),
    )

    paths = run_analysis_review(contest_path=contest, response_path=response, output_dir=tmp_path / "out")

    proposed = paths["proposed_yaml"].read_text(encoding="utf-8")
    assert "problem:\n  task_type: classification" in proposed
    assert "rules:\n  external_api_allowed: false" in proposed
    assert read_simple_yaml(paths["proposed_yaml"]) == {
        "problem": {"task_type": "classification"},
        "rules": {"external_api_allowed": False},
    }


def test_code_agent_task_plan_generation():
    text = render_code_agent_task_plan([
        {
            "title": "Add classification loader candidate",
            "priority": "P1",
            "files": ["templates/base_harness/src/loader.py"],
            "acceptance_criteria": ["테스트가 통과한다."],
        }
    ])

    assert "# Code Agent Task Plan" in text
    assert "Add classification loader candidate" in text
    assert "templates/base_harness/src/loader.py" in text
    assert "테스트가 통과한다." in text


def test_empty_proposed_overrides_mapping_when_no_accepted_candidates():
    assert build_proposed_overrides([]) == {}
