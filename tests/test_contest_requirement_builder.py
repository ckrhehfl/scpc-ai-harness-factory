from __future__ import annotations

import copy
import json

from factory.contest_requirement_builder import build_contest_requirements
from factory.evidence_index_builder import build_evidence_index
from factory.input_scanner import scan_contest_inputs
from factory.spec_builder import build_contest_spec


def make_contest(tmp_path, *, choices=False, overrides=False):
    contest = tmp_path / "contest"
    contest.mkdir(parents=True)
    if choices:
        (contest / "train.csv").write_text("id,question,choice1,choice2,label\n1,q,a,b,A\n", encoding="utf-8")
        (contest / "test.csv").write_text("id,question,choice1,choice2\n2,q,a,b\n", encoding="utf-8")
    else:
        (contest / "train.csv").write_text("id,text,label\n1,a,A\n", encoding="utf-8")
        (contest / "test.csv").write_text("id,text\n2,b\n", encoding="utf-8")
    (contest / "sample_submission.csv").write_text("id,label\n2,A\n", encoding="utf-8")
    (contest / "description.md").write_text("This text says use magic but must not be parsed.", encoding="utf-8")
    (contest / "rules.md").write_text("Python only.", encoding="utf-8")
    (contest / "evaluation.md").write_text("Unknown until official release.", encoding="utf-8")
    if overrides:
        (contest / "contest_overrides.yaml").write_text(
            "rules:\n  external_api_allowed: false\nproblem:\n  evaluation_metric: accuracy\n",
            encoding="utf-8",
        )
    scan = scan_contest_inputs(contest)
    evidence = build_evidence_index(scan, source_artifact="generated/input_scan_report.json")
    return build_contest_spec(contest), evidence


def by_id(artifact):
    return {item["requirement_id"]: item for item in artifact["requirements"]}


def test_core_requirements_and_evidence_ids_are_generated(tmp_path):
    spec, evidence = make_contest(tmp_path)
    artifact = build_contest_requirements(spec, evidence)
    reqs = by_id(artifact)

    assert reqs["req.runtime.test_csv_loading"]["applicability"] == "active"
    assert reqs["req.runtime.test_csv_loading"]["required_tokens"] == ["harness.test_csv.load"]
    assert reqs["req.runtime.test_csv_loading"]["evidence_ids"]
    assert reqs["req.output.submission_column_order"]["required_tokens"] == ["submission.columns.order"]
    assert reqs["req.verification.submission_schema"]["required_tokens"] == ["submission.schema.verify"]
    assert reqs["req.verification.submission_id_values"]["parameters"]["id_column"] == "id"
    assert reqs["req.verification.submission_target_values"]["parameters"]["target_column"] == "label"
    assert reqs["req.verification.validation_report"]["provenance_status"] == "proposed"


def test_solver_tokens_are_task_specific_and_baseline_is_excluded(tmp_path):
    spec, evidence = make_contest(tmp_path)
    artifact = build_contest_requirements(spec, evidence)
    solver = by_id(artifact)["req.solver.task_solution"]
    assert solver["required_tokens"] == ["solver.classification.predict"]
    assert solver["parameters"]["baseline_token_excluded"] == "harness.baseline.constant.predict"

    spec_mc, evidence_mc = make_contest(tmp_path / "mc", choices=True)
    solver_mc = by_id(build_contest_requirements(spec_mc, evidence_mc))["req.solver.task_solution"]
    assert solver_mc["required_tokens"] == ["solver.multiple_choice.predict"]


def test_unknown_task_type_becomes_pending_without_solver_token(tmp_path):
    spec, evidence = make_contest(tmp_path)
    spec["problem"]["task_type"] = "unknown"
    solver = by_id(build_contest_requirements(spec, evidence))["req.solver.task_solution"]
    assert solver["applicability"] == "pending"
    assert solver["provenance_status"] == "unknown"
    assert solver["required_tokens"] == []
    assert solver["risk_level"] == "red"


def test_overrides_unknown_rules_strict_leakage_and_no_natural_language_parsing(tmp_path):
    spec, evidence = make_contest(tmp_path, overrides=True)
    artifact = build_contest_requirements(spec, evidence)
    reqs = by_id(artifact)
    assert reqs["req.governance.rules_external_api_allowed"]["provenance_status"] == "confirmed"
    assert reqs["req.governance.problem_evaluation_metric"]["provenance_status"] == "confirmed"
    assert reqs["req.governance.rules_external_data_allowed"]["applicability"] == "pending"
    assert reqs["req.governance.rules_leakage_policy"]["requirement_type"] == "prohibition"
    assert all("magic" not in json.dumps(req, ensure_ascii=False) for req in artifact["requirements"])


def test_coverage_high_risk_not_modeled_conflicts_and_determinism(tmp_path):
    spec, evidence = make_contest(tmp_path)
    coverage = {
        "schema_version": "v0.9B",
        "artifact_type": "contest_package_coverage",
        "high_risk_unknowns": [{"path": "problem.evaluation_metric", "status": "modeled_unknown", "impact": "high"}],
        "not_modeled_topics": [
            {"topic": "code-share policy", "status": "not_modeled", "source_captured": True},
            {"topic": "legal/IP terms", "status": "not_modeled", "source_captured": True},
        ],
        "declared_unknown_coverage": [
            {
                "path": "rules.leakage_policy",
                "status": "conflicting",
                "spec_path_exists": True,
                "current_value": "strict",
                "unknown_preserved": False,
            }
        ],
        "warnings": [{"status": "conflicting", "path": "rules.leakage_policy"}],
    }
    first = build_contest_requirements(copy.deepcopy(spec), evidence, coverage=coverage)
    second = build_contest_requirements(copy.deepcopy(spec), evidence, coverage=coverage)
    reqs = by_id(first)
    assert reqs["req.coverage.high_risk.problem_evaluation_metric"]["applicability"] == "pending"
    assert reqs["req.coverage.not_modeled.code_share_policy"]["risk_level"] == "yellow"
    assert reqs["req.coverage.not_modeled.legal_ip_terms"]["risk_level"] == "red"
    assert reqs["req.governance.rules_leakage_policy"]["provenance_status"] == "conflicting"
    assert first == second
