from __future__ import annotations

import copy

import pytest

from factory.capability_model import CapabilityModelError, validate_capability_definition


def valid_capability(capability_id: str = "cap.factory.input_scan") -> dict:
    return {
        "capability_id": capability_id,
        "name": "Input scan",
        "scope": "factory",
        "category": "intake",
        "declared_status": "implemented",
        "description": "Scans inputs.",
        "provides": ["contest.input.scan"],
        "inputs": ["contest_directory"],
        "outputs": ["input_scan_report.json"],
        "implementation_evidence": [{"path": "factory/input_scanner.py", "symbols": ["scan_contest_inputs"]}],
        "test_evidence": [{"path": "tests/test_input_scanner.py", "symbols": ["test_scan_contest_inputs_collects_files_documents_and_csv_preview"]}],
        "dependencies": [],
        "risk_gates": [],
        "limitations": ["Text extraction only."],
        "tags": ["offline"],
    }


def valid_definition() -> dict:
    return {
        "schema_version": "v0.10A",
        "artifact_type": "capability_registry_definition",
        "capabilities": [valid_capability()],
    }


def assert_invalid(definition: dict) -> None:
    with pytest.raises(CapabilityModelError):
        validate_capability_definition(definition)


def test_valid_definition_is_allowed():
    validate_capability_definition(valid_definition())


def test_bad_schema_version_is_rejected():
    definition = valid_definition()
    definition["schema_version"] = "v0.10"
    assert_invalid(definition)


def test_bad_artifact_type_is_rejected():
    definition = valid_definition()
    definition["artifact_type"] = "capability_registry"
    assert_invalid(definition)


def test_duplicate_capability_id_is_rejected():
    definition = valid_definition()
    definition["capabilities"].append(copy.deepcopy(definition["capabilities"][0]))
    assert_invalid(definition)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("capability_id", "factory.input_scan"),
        ("scope", "runtime"),
        ("category", "matching"),
        ("declared_status", "done"),
    ],
)
def test_invalid_capability_fixed_fields_are_rejected(field, value):
    definition = valid_definition()
    definition["capabilities"][0][field] = value
    assert_invalid(definition)


def test_duplicate_provides_are_rejected():
    definition = valid_definition()
    definition["capabilities"][0]["provides"] = ["contest.input.scan", "contest.input.scan"]
    assert_invalid(definition)


def test_invalid_provides_token_is_rejected():
    definition = valid_definition()
    definition["capabilities"][0]["provides"] = ["Contest Input Scan"]
    assert_invalid(definition)


def test_unknown_dependency_is_rejected():
    definition = valid_definition()
    definition["capabilities"][0]["dependencies"] = ["cap.factory.missing"]
    assert_invalid(definition)


def test_self_dependency_is_rejected():
    definition = valid_definition()
    definition["capabilities"][0]["dependencies"] = ["cap.factory.input_scan"]
    assert_invalid(definition)


def test_dependency_cycle_is_rejected():
    first = valid_capability("cap.factory.first")
    second = valid_capability("cap.factory.second")
    first["dependencies"] = ["cap.factory.second"]
    second["dependencies"] = ["cap.factory.first"]
    definition = valid_definition()
    definition["capabilities"] = [first, second]
    assert_invalid(definition)


def test_implemented_without_implementation_evidence_is_rejected():
    definition = valid_definition()
    definition["capabilities"][0]["implementation_evidence"] = []
    assert_invalid(definition)


def test_implemented_without_test_evidence_is_rejected():
    definition = valid_definition()
    definition["capabilities"][0]["test_evidence"] = []
    assert_invalid(definition)


def test_planned_without_evidence_is_allowed():
    definition = valid_definition()
    capability = definition["capabilities"][0]
    capability["declared_status"] = "planned"
    capability["implementation_evidence"] = []
    capability["test_evidence"] = []
    validate_capability_definition(definition)
