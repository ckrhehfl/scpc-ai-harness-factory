from __future__ import annotations

from pathlib import Path
import copy
import json

import pytest

from factory.capability_model import CapabilityModelError
from factory.capability_registry_builder import (
    audit_capability_registry,
    load_capability_definition,
    render_capability_registry_markdown,
    save_capability_registry,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def capability(
    *,
    capability_id: str = "cap.factory.sample",
    status: str = "implemented",
    implementation_path: str = "module.py",
    implementation_symbols: list[str] | None = None,
    test_path: str = "test_module.py",
    test_symbols: list[str] | None = None,
    dependencies: list[str] | None = None,
) -> dict:
    return {
        "capability_id": capability_id,
        "name": "Sample capability",
        "scope": "factory",
        "category": "audit",
        "declared_status": status,
        "description": "A sample capability.",
        "provides": [f"sample.{capability_id.rsplit('.', 1)[-1]}.token"],
        "inputs": ["input"],
        "outputs": ["output"],
        "implementation_evidence": (
            [{"path": implementation_path, "symbols": implementation_symbols or ["build_sample"]}]
            if implementation_path
            else []
        ),
        "test_evidence": (
            [{"path": test_path, "symbols": test_symbols or ["test_sample"]}]
            if test_path
            else []
        ),
        "dependencies": dependencies or [],
        "risk_gates": [],
        "limitations": ["Only validates static evidence."],
        "tags": ["offline"],
    }


def definition(*capabilities: dict) -> dict:
    return {
        "schema_version": "v0.10A",
        "artifact_type": "capability_registry_definition",
        "capabilities": list(capabilities),
    }


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "module.py").write_text(
        "def build_sample():\n    raise RuntimeError('not executed')\n\nclass SampleClass:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "test_module.py").write_text(
        "def test_sample():\n    pass\n\nclass TestSample:\n    pass\n",
        encoding="utf-8",
    )
    return tmp_path


def test_python_path_and_function_symbol_are_verified(repo: Path):
    registry = audit_capability_registry(definition(capability()), repo, "registry.json")
    item = registry["capabilities"][0]
    assert item["verification_status"] == "verified"
    assert item["matching_eligibility"] == "eligible"
    assert item["evidence_audit"]["implementation"] == [{"path": "module.py", "symbols": ["build_sample"]}]


def test_class_symbol_is_verified(repo: Path):
    cap = capability(implementation_symbols=["SampleClass"], test_symbols=["TestSample"])
    registry = audit_capability_registry(definition(cap), repo, "registry.json")
    assert registry["summary"]["verified"] == 1


def test_missing_path_makes_capability_incomplete(repo: Path):
    cap = capability(implementation_path="missing.py")
    registry = audit_capability_registry(definition(cap), repo, "registry.json")
    item = registry["capabilities"][0]
    assert item["verification_status"] == "incomplete"
    assert item["matching_eligibility"] == "ineligible"
    assert item["evidence_audit"]["missing_paths"] == ["missing.py"]


def test_missing_symbol_makes_capability_incomplete(repo: Path):
    cap = capability(implementation_symbols=["missing_symbol"])
    registry = audit_capability_registry(definition(cap), repo, "registry.json")
    item = registry["capabilities"][0]
    assert item["verification_status"] == "incomplete"
    assert item["evidence_audit"]["missing_symbols"] == [
        {"path": "module.py", "symbol": "missing_symbol", "group": "implementation"}
    ]


def test_syntax_error_makes_capability_incomplete(repo: Path):
    (repo / "module.py").write_text("def broken(:\n", encoding="utf-8")
    registry = audit_capability_registry(definition(capability()), repo, "registry.json")
    item = registry["capabilities"][0]
    assert item["verification_status"] == "incomplete"
    assert any("parse failed" in warning for warning in item["evidence_audit"]["warnings"])


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/tmp/module.py",
        "C:/repo/module.py",
        "../module.py",
        "generated/module.py",
    ],
)
def test_unsafe_evidence_paths_are_rejected(repo: Path, unsafe_path: str):
    cap = capability(implementation_path=unsafe_path)
    with pytest.raises(CapabilityModelError):
        audit_capability_registry(definition(cap), repo, "registry.json")


def test_directory_path_is_rejected(repo: Path):
    cap = capability(implementation_path="pkg")
    (repo / "pkg").mkdir()
    with pytest.raises(CapabilityModelError):
        audit_capability_registry(definition(cap), repo, "registry.json")


def test_repository_escape_symlink_is_rejected(repo: Path, tmp_path: Path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("def build_sample():\n    pass\n", encoding="utf-8")
    (repo / "escape.py").symlink_to(outside)
    cap = capability(implementation_path="escape.py")
    with pytest.raises(CapabilityModelError):
        audit_capability_registry(definition(cap), repo, "registry.json")


def test_ast_symbol_scan_does_not_import_or_execute_code(repo: Path):
    (repo / "module.py").write_text(
        "raise RuntimeError('import would execute this')\n\ndef build_sample():\n    return 1\n",
        encoding="utf-8",
    )
    registry = audit_capability_registry(definition(capability()), repo, "registry.json")
    assert registry["summary"]["eligible"] == 1


def test_status_computation_for_implemented_partial_planned_and_deprecated(repo: Path):
    implemented = capability(capability_id="cap.factory.implemented")
    partial = capability(
        capability_id="cap.factory.partial",
        status="partial",
        test_path="",
        dependencies=["cap.factory.implemented"],
    )
    planned = capability(
        capability_id="cap.factory.planned",
        status="planned",
        implementation_path="",
        test_path="",
        dependencies=["cap.factory.partial"],
    )
    deprecated = capability(
        capability_id="cap.factory.deprecated",
        status="deprecated",
        dependencies=["cap.factory.implemented"],
    )
    registry = audit_capability_registry(
        definition(implemented, partial, planned, deprecated),
        repo,
        "registry.json",
    )
    by_id = {item["capability_id"]: item for item in registry["capabilities"]}
    assert by_id["cap.factory.implemented"]["matching_eligibility"] == "eligible"
    assert by_id["cap.factory.partial"]["matching_eligibility"] == "limited"
    assert by_id["cap.factory.partial"]["verification_status"] == "verified"
    assert by_id["cap.factory.planned"]["verification_status"] == "not_applicable"
    assert by_id["cap.factory.planned"]["matching_eligibility"] == "ineligible"
    assert by_id["cap.factory.deprecated"]["matching_eligibility"] == "ineligible"
    assert registry["summary"]["total"] == 4
    assert registry["summary"]["eligible"] == 1
    assert registry["summary"]["limited"] == 1
    assert registry["summary"]["ineligible"] == 2


def test_capabilities_are_sorted_and_output_is_deterministic(repo: Path):
    first = capability(capability_id="cap.factory.zeta")
    second = capability(capability_id="cap.factory.alpha")
    registry_a = audit_capability_registry(definition(first, second), repo, "registry.json")
    registry_b = audit_capability_registry(definition(first, second), repo, "registry.json")
    ids = [item["capability_id"] for item in registry_a["capabilities"]]
    assert ids == ["cap.factory.alpha", "cap.factory.zeta"]
    assert json.dumps(registry_a, ensure_ascii=False, sort_keys=True) == json.dumps(
        registry_b,
        ensure_ascii=False,
        sort_keys=True,
    )


def test_output_does_not_include_absolute_local_paths(repo: Path):
    registry = audit_capability_registry(definition(capability()), repo, "registry.json")
    rendered = json.dumps(registry, ensure_ascii=False)
    assert str(repo) not in rendered


def test_markdown_renders_required_sections(repo: Path):
    registry = audit_capability_registry(definition(capability()), repo, "registry.json")
    markdown = render_capability_registry_markdown(registry)
    assert "verified는 코드 및 테스트 근거" in markdown
    assert "## Scope Counts" in markdown
    assert "#### Implementation Evidence" in markdown


def test_save_capability_registry_writes_json_and_markdown(repo: Path, tmp_path: Path):
    registry = audit_capability_registry(definition(capability()), repo, "registry.json")
    paths = save_capability_registry(registry, tmp_path / "generated")
    assert paths["json"].exists()
    assert paths["md"].exists()


def test_checked_in_registry_is_structurally_valid_and_verified():
    source = REPO_ROOT / "capabilities" / "registry.json"
    loaded = load_capability_definition(source)
    registry = audit_capability_registry(loaded, REPO_ROOT, "capabilities/registry.json")
    assert registry["summary"]["total"] == len(registry["capabilities"])
    assert registry["summary"]["incomplete"] == 0
    assert registry["summary"]["ineligible"] == 0
    ids = [item["capability_id"] for item in registry["capabilities"]]
    assert len(ids) == len(set(ids))
    provides = [token for item in registry["capabilities"] for token in item["provides"]]
    assert len(provides) == len(set(provides))
    forbidden = json.dumps(loaded, ensure_ascii=False).lower()
    for token in [
        "ocr",
        "dacon login",
        "dacon crawling",
        "submission upload",
        "external llm runtime execution",
        "requirement-capability matching",
        "automatic git",
    ]:
        assert token not in forbidden
    for item in loaded["capabilities"]:
        assert item["limitations"]
        evidence_paths = [entry["path"] for key in ["implementation_evidence", "test_evidence"] for entry in item[key]]
        assert not any(path.startswith(("generated/", "runs/", "contests/")) for path in evidence_paths)
