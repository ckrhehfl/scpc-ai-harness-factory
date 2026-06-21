from __future__ import annotations

import json

from factory.contest_package_coverage import build_contest_package_coverage
from factory.evidence_index_builder import build_evidence_index
from factory.input_scanner import scan_contest_inputs
from factory.spec_builder import build_contest_spec
from factory.utils import write_json


def make_package(tmp_path):
    contest = tmp_path / "contest"
    (contest / "raw").mkdir(parents=True)
    (contest / "ui").mkdir()
    (contest / "raw" / "official_notice.txt").write_text("A" * 4001, encoding="utf-8")
    (contest / "ui" / "submit.png").write_bytes(b"png")
    (contest / "train.csv").write_text("id,text,label\n1,a,A\n", encoding="utf-8")
    (contest / "test.csv").write_text("id,text\n2,b\n", encoding="utf-8")
    (contest / "sample_submission.csv").write_text("id,label\n2,A\n", encoding="utf-8")
    (contest / "contest_package.json").write_text(
        json.dumps(
            {
                "schema_version": "v0.9B",
                "contest": {"name": "2026 SCPC AI Challenge", "phase": "preannouncement"},
                "sources": [
                    {
                        "path": "raw/official_notice.txt",
                        "role": "official_notice",
                        "source_kind": "document",
                        "visibility": "public",
                    },
                    {
                        "path": "ui/submit.png",
                        "role": "submission_ui_capture",
                        "source_kind": "image",
                        "visibility": "public",
                    },
                ],
                "declared_unknowns": [
                    "problem.evaluation_metric",
                    "rules.external_api_allowed",
                ],
            }
        ),
        encoding="utf-8",
    )
    return contest


def write_artifacts(contest, artifacts, spec=None):
    scan = scan_contest_inputs(contest)
    evidence = build_evidence_index(scan, source_artifact=str(artifacts / "input_scan_report.json"))
    write_json(artifacts / "input_scan_report.json", scan)
    write_json(artifacts / "evidence_index.json", evidence)
    write_json(artifacts / "contest_spec.json", spec or build_contest_spec(contest))
    return scan, evidence


def test_coverage_links_manifest_sources_scan_and_evidence(tmp_path):
    contest = make_package(tmp_path)
    artifacts = tmp_path / "generated"
    _, evidence = write_artifacts(contest, artifacts)

    coverage = build_contest_package_coverage(contest, artifacts_dir=artifacts)

    assert coverage["schema_version"] == "v0.9B"
    assert coverage["artifact_type"] == "contest_package_coverage"
    assert coverage["manifest_present"] is True
    by_path = {item["path"]: item for item in coverage["source_coverage"]}
    doc = by_path["raw/official_notice.txt"]
    assert doc["status"] == "captured"
    assert doc["role"] == "official_notice"
    assert len(doc["document_chunk_evidence_ids"]) == 2
    image = by_path["ui/submit.png"]
    assert image["status"] == "captured"
    assert image["inventory_evidence_ids"]
    assert not image["document_chunk_evidence_ids"]
    assert coverage["source_summary"]["document_chunk_evidence_count"] == 2
    assert any(":document_chunk:" in record["key"] for record in evidence["records"])


def test_coverage_classifies_core_fields_declared_unknowns_and_risks(tmp_path):
    contest = make_package(tmp_path)
    artifacts = tmp_path / "generated"
    spec = build_contest_spec(contest)
    spec["problem"]["evaluation_metric"] = "accuracy"
    write_artifacts(contest, artifacts, spec=spec)

    coverage = build_contest_package_coverage(contest, artifacts_dir=artifacts)

    core = {item["path"]: item for item in coverage["core_field_coverage"]}
    assert core["problem.task_type"]["status"] == "modeled_confirmed"
    assert core["rules.allowed_language"]["status"] == "modeled_unknown"
    assert core["rules.external_api_allowed"]["status"] == "modeled_unknown"
    assert core["output.required_file"]["status"] == "modeled_confirmed"
    declared = {item["path"]: item for item in coverage["declared_unknown_coverage"]}
    assert declared["problem.evaluation_metric"]["status"] == "conflicting"
    assert declared["rules.external_api_allowed"]["status"] == "modeled_unknown"
    assert any(warning["path"] == "problem.evaluation_metric" for warning in coverage["warnings"])
    risk_paths = {item["path"] for item in coverage["high_risk_unknowns"]}
    assert "rules.external_api_allowed" in risk_paths
    assert "finalist.code_submission_format" in risk_paths
    topics = {item["topic"]: item for item in coverage["not_modeled_topics"]}
    assert topics["code-share policy"]["status"] == "not_modeled"
    assert topics["round schedule"]["source_captured"] is True


def test_declared_unknown_with_human_override_reports_override_without_conflict(tmp_path):
    contest = make_package(tmp_path)
    (contest / "contest_overrides.yaml").write_text(
        "problem:\n  evaluation_metric: accuracy\n", encoding="utf-8"
    )
    artifacts = tmp_path / "generated"
    write_artifacts(contest, artifacts)

    coverage = build_contest_package_coverage(contest, artifacts_dir=artifacts)

    declared = {item["path"]: item for item in coverage["declared_unknown_coverage"]}
    assert declared["problem.evaluation_metric"]["status"] == "modeled_confirmed"
    assert declared["problem.evaluation_metric"]["override"]["status"] == "override_applied"
    assert not any(warning.get("path") == "problem.evaluation_metric" for warning in coverage["warnings"])


def test_coverage_does_not_modify_input_artifacts(tmp_path):
    contest = make_package(tmp_path)
    artifacts = tmp_path / "generated"
    write_artifacts(contest, artifacts)
    before = {
        path.name: path.read_text(encoding="utf-8")
        for path in [
            artifacts / "input_scan_report.json",
            artifacts / "evidence_index.json",
            artifacts / "contest_spec.json",
        ]
    }

    build_contest_package_coverage(contest, artifacts_dir=artifacts)

    after = {path.name: path.read_text(encoding="utf-8") for path in artifacts.iterdir()}
    for name, text in before.items():
        assert after[name] == text
