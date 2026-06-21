from __future__ import annotations

import json

from factory.evidence_index_builder import build_evidence_index
from factory.input_scanner import scan_contest_inputs
from factory.run_contest_package_coverage import main
from factory.spec_builder import build_contest_spec
from factory.utils import write_json


def make_package(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    (contest / "raw.txt").write_text("official", encoding="utf-8")
    (contest / "train.csv").write_text("id,label\n1,A\n", encoding="utf-8")
    (contest / "test.csv").write_text("id\n2\n", encoding="utf-8")
    (contest / "sample_submission.csv").write_text("id,label\n2,A\n", encoding="utf-8")
    (contest / "contest_package.json").write_text(
        json.dumps(
            {
                "schema_version": "v0.9B",
                "contest": {"name": "SCPC", "phase": "preannouncement"},
                "sources": [
                    {
                        "path": "raw.txt",
                        "role": "official_notice",
                        "source_kind": "document",
                        "visibility": "public",
                    }
                ],
                "declared_unknowns": ["problem.evaluation_metric"],
            }
        ),
        encoding="utf-8",
    )
    return contest


def write_artifacts(contest, artifacts):
    scan = scan_contest_inputs(contest)
    write_json(artifacts / "input_scan_report.json", scan)
    write_json(
        artifacts / "evidence_index.json",
        build_evidence_index(scan, source_artifact=str(artifacts / "input_scan_report.json")),
    )
    write_json(artifacts / "contest_spec.json", build_contest_spec(contest))


def run_cli(monkeypatch, contest, artifacts, output):
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_contest_package_coverage.py",
            "--contest",
            str(contest),
            "--artifacts",
            str(artifacts),
            "--output",
            str(output),
        ],
    )
    return main()


def test_cli_generates_coverage_outputs(tmp_path, monkeypatch, capsys):
    contest = make_package(tmp_path)
    artifacts = tmp_path / "generated"
    output = tmp_path / "coverage"
    write_artifacts(contest, artifacts)
    source_before = (contest / "raw.txt").read_text(encoding="utf-8")
    overrides_before = (contest / "contest_overrides.yaml").read_text(encoding="utf-8") if (contest / "contest_overrides.yaml").exists() else None

    code = run_cli(monkeypatch, contest, artifacts, output)
    captured = capsys.readouterr()

    assert code == 0
    assert "[OK] Contest package coverage generated" in captured.out
    assert (output / "contest_package_coverage.json").exists()
    assert (output / "contest_package_coverage.md").exists()
    assert (contest / "raw.txt").read_text(encoding="utf-8") == source_before
    if overrides_before is not None:
        assert (contest / "contest_overrides.yaml").read_text(encoding="utf-8") == overrides_before


def test_cli_returns_nonzero_for_manifest_error_without_outputs(tmp_path, monkeypatch):
    contest = make_package(tmp_path)
    artifacts = tmp_path / "generated"
    output = tmp_path / "coverage"
    write_artifacts(contest, artifacts)
    (contest / "contest_package.json").write_text("{bad", encoding="utf-8")

    assert run_cli(monkeypatch, contest, artifacts, output) == 1
    assert not (output / "contest_package_coverage.json").exists()
    assert not (output / "contest_package_coverage.md").exists()


def test_cli_returns_nonzero_for_missing_artifact_without_outputs(tmp_path, monkeypatch):
    contest = make_package(tmp_path)
    artifacts = tmp_path / "generated"
    output = tmp_path / "coverage"
    artifacts.mkdir()

    assert run_cli(monkeypatch, contest, artifacts, output) == 1
    assert not (output / "contest_package_coverage.json").exists()


def test_cli_returns_nonzero_for_malformed_artifact_without_outputs(tmp_path, monkeypatch):
    contest = make_package(tmp_path)
    artifacts = tmp_path / "generated"
    output = tmp_path / "coverage"
    write_artifacts(contest, artifacts)
    (artifacts / "contest_spec.json").write_text("{bad", encoding="utf-8")

    assert run_cli(monkeypatch, contest, artifacts, output) == 1
    assert not (output / "contest_package_coverage.json").exists()
