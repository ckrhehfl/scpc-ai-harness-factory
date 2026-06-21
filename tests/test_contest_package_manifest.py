from __future__ import annotations

import json

import pytest

from factory.contest_package_manifest import (
    ContestPackageManifestError,
    build_manifest_source_map,
    load_contest_package_manifest,
)


def write_manifest(contest, manifest):
    (contest / "contest_package.json").write_text(json.dumps(manifest), encoding="utf-8")


def valid_manifest(path="raw/official_notice.txt") -> dict:
    return {
        "schema_version": "v0.9B",
        "contest": {"name": "2026 SCPC AI Challenge", "phase": "preannouncement", "platform": "Dacon"},
        "sources": [
            {
                "path": path,
                "role": "official_notice",
                "source_kind": "document",
                "visibility": "public",
                "origin": "Dacon contest guide export",
            }
        ],
        "declared_unknowns": ["problem.evaluation_metric"],
    }


def make_contest(tmp_path):
    contest = tmp_path / "contest"
    (contest / "raw").mkdir(parents=True)
    (contest / "raw" / "official_notice.txt").write_text("notice", encoding="utf-8")
    return contest


def test_loads_valid_manifest_and_builds_source_map(tmp_path):
    contest = make_contest(tmp_path)
    manifest = valid_manifest()
    write_manifest(contest, manifest)

    loaded = load_contest_package_manifest(contest)
    assert loaded == manifest
    assert build_manifest_source_map(loaded)["raw/official_notice.txt"]["role"] == "official_notice"


def test_missing_manifest_returns_none(tmp_path):
    contest = make_contest(tmp_path)
    assert load_contest_package_manifest(contest) is None
    assert build_manifest_source_map(None) == {}


def test_rejects_malformed_json(tmp_path):
    contest = make_contest(tmp_path)
    (contest / "contest_package.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(ContestPackageManifestError):
        load_contest_package_manifest(contest)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.update({"schema_version": "v0.9A"}),
        lambda m: m["sources"][0].update({"path": "/raw/official_notice.txt"}),
        lambda m: m["sources"][0].update({"path": "C:/raw/official_notice.txt"}),
        lambda m: m["sources"][0].update({"path": "../official_notice.txt"}),
        lambda m: m["sources"].append(dict(m["sources"][0])),
        lambda m: m["sources"][0].update({"path": "raw/missing.txt"}),
        lambda m: m["sources"][0].update({"source_kind": "webpage"}),
        lambda m: m["sources"][0].update({"visibility": "secret"}),
        lambda m: m.update({"declared_unknowns": ["evaluation_metric"]}),
    ],
)
def test_rejects_invalid_manifest_shapes(tmp_path, mutate):
    contest = make_contest(tmp_path)
    manifest = valid_manifest()
    mutate(manifest)
    write_manifest(contest, manifest)

    with pytest.raises(ContestPackageManifestError):
        load_contest_package_manifest(contest)


def test_rejects_manifest_as_source(tmp_path):
    contest = make_contest(tmp_path)
    manifest = valid_manifest("contest_package.json")
    write_manifest(contest, manifest)

    with pytest.raises(ContestPackageManifestError):
        load_contest_package_manifest(contest)
