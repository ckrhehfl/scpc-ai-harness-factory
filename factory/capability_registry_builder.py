from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import copy
import json

from factory.capability_model import (
    CapabilityModelError,
    REGISTRY_ARTIFACT_TYPE,
    SCHEMA_VERSION,
    python_top_level_symbols,
    resolve_evidence_file,
    validate_capability_definition,
)
from factory.utils import write_json, write_text


SUMMARY_KEYS = ["eligible", "limited", "ineligible", "verified", "incomplete", "not_applicable"]


def load_capability_definition(path: str | Path) -> dict[str, Any]:
    registry_path = Path(path)
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CapabilityModelError(f"Malformed capability registry JSON: {exc}") from exc
    except OSError as exc:
        raise CapabilityModelError(f"Could not read capability registry: {exc}") from exc
    if not isinstance(data, dict):
        raise CapabilityModelError("Capability registry definition must be a JSON object")
    validate_capability_definition(data)
    return data


def audit_capability_registry(
    definition: dict[str, Any],
    repo_root: str | Path,
    source_registry: str,
) -> dict[str, Any]:
    validate_capability_definition(definition)
    capabilities = []
    warnings: list[str] = []
    for source_capability in definition["capabilities"]:
        capability = copy.deepcopy(source_capability)
        audit = {
            "implementation": [],
            "tests": [],
            "missing_paths": [],
            "missing_symbols": [],
            "warnings": [],
        }
        _audit_evidence_group(capability.get("implementation_evidence", []), repo_root, audit, "implementation")
        _audit_evidence_group(capability.get("test_evidence", []), repo_root, audit, "tests")
        _apply_statuses(capability, audit)
        capability["evidence_audit"] = audit
        for warning in audit["warnings"]:
            warnings.append(f"{capability['capability_id']}: {warning}")
        capabilities.append(capability)

    capabilities.sort(key=lambda item: item["capability_id"])
    registry = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": REGISTRY_ARTIFACT_TYPE,
        "source_registry": source_registry,
        "summary": _build_summary(capabilities),
        "capabilities": capabilities,
        "warnings": warnings,
    }
    return registry


def render_capability_registry_markdown(registry: dict[str, Any]) -> str:
    capabilities = registry.get("capabilities", [])
    summary = registry.get("summary", {})
    scope_counts = Counter(item.get("scope") for item in capabilities)
    category_counts = Counter(item.get("category") for item in capabilities)
    eligibility_counts = Counter(item.get("matching_eligibility") for item in capabilities)
    verification_counts = Counter(item.get("verification_status") for item in capabilities)

    lines = [
        "# Capability Registry",
        "",
        "verified는 코드 및 테스트 근거가 저장소에서 확인됐다는 뜻이며,",
        "공식 규칙 확인, 사람 승인, 모든 대회 지원 또는 성능 보장을 뜻하지 않는다.",
        "",
        "## Summary",
        "",
        f"- total: {summary.get('total', 0)}",
    ]
    for key in SUMMARY_KEYS:
        lines.append(f"- {key}: {summary.get(key, 0)}")

    _append_counts(lines, "Scope Counts", scope_counts)
    _append_counts(lines, "Category Counts", category_counts)
    _append_counts(lines, "Eligibility Counts", eligibility_counts)
    _append_counts(lines, "Verification Counts", verification_counts)

    lines.extend(["", "## Capabilities", ""])
    for capability in capabilities:
        lines.extend([
            f"### {capability['capability_id']}",
            "",
            f"- name: {capability.get('name')}",
            f"- scope: {capability.get('scope')}",
            f"- category: {capability.get('category')}",
            f"- declared_status: {capability.get('declared_status')}",
            f"- verification_status: {capability.get('verification_status')}",
            f"- matching_eligibility: {capability.get('matching_eligibility')}",
            f"- description: {capability.get('description')}",
            "",
            "#### Provides",
            "",
            _bullet(capability.get("provides", [])),
            "",
            "#### Inputs",
            "",
            _bullet(capability.get("inputs", [])),
            "",
            "#### Outputs",
            "",
            _bullet(capability.get("outputs", [])),
            "",
            "#### Implementation Evidence",
            "",
            _evidence_lines(capability.get("implementation_evidence", [])),
            "",
            "#### Test Evidence",
            "",
            _evidence_lines(capability.get("test_evidence", [])),
            "",
            "#### Dependencies",
            "",
            _bullet(capability.get("dependencies", [])),
            "",
            "#### Risk Gates",
            "",
            _bullet(capability.get("risk_gates", [])),
            "",
            "#### Limitations",
            "",
            _bullet(capability.get("limitations", [])),
            "",
            "#### Warnings",
            "",
            _audit_warning_lines(capability.get("evidence_audit", {})),
            "",
        ])

    if registry.get("warnings"):
        lines.extend(["## Registry Warnings", "", _bullet(registry["warnings"]), ""])
    return "\n".join(lines).rstrip() + "\n"


def save_capability_registry(registry: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    out = Path(output_dir)
    return {
        "json": write_json(out / "capability_registry.json", registry),
        "md": write_text(out / "capability_registry.md", render_capability_registry_markdown(registry)),
    }


def _audit_evidence_group(
    entries: list[dict[str, Any]],
    repo_root: str | Path,
    audit: dict[str, list[Any]],
    group: str,
) -> None:
    for entry in entries:
        path_text = entry["path"]
        try:
            resolved = resolve_evidence_file(repo_root, path_text)
        except CapabilityModelError:
            raise
        if not resolved.exists():
            audit["missing_paths"].append(path_text)
            audit["warnings"].append(f"{group} evidence path missing: {path_text}")
            continue
        if resolved.suffix != ".py":
            audit["warnings"].append(f"{group} evidence is not a Python file and cannot be symbol-audited: {path_text}")
            continue
        try:
            available_symbols = python_top_level_symbols(resolved)
        except CapabilityModelError as exc:
            audit["warnings"].append(f"{group} evidence parse failed for {path_text}: {exc}")
            continue

        missing = [symbol for symbol in entry["symbols"] if symbol not in available_symbols]
        if missing:
            for symbol in missing:
                audit["missing_symbols"].append({"path": path_text, "symbol": symbol, "group": group})
            audit["warnings"].append(f"{group} evidence symbol missing in {path_text}: {', '.join(missing)}")
            continue
        audit[group].append({"path": path_text, "symbols": list(entry["symbols"])})


def _apply_statuses(capability: dict[str, Any], audit: dict[str, list[Any]]) -> None:
    status = capability["declared_status"]
    failures = bool(audit["missing_paths"] or audit["missing_symbols"] or audit["warnings"])
    implementation_count = len(capability.get("implementation_evidence", []))
    verified_implementation_count = len(audit["implementation"])
    tests_count = len(capability.get("test_evidence", []))
    verified_tests_count = len(audit["tests"])

    if status == "planned":
        capability["verification_status"] = "not_applicable"
        capability["matching_eligibility"] = "ineligible"
        return
    if status == "deprecated":
        capability["verification_status"] = "verified" if not failures else "incomplete"
        capability["matching_eligibility"] = "ineligible"
        return
    if status == "implemented":
        verified = (
            not failures
            and implementation_count > 0
            and tests_count > 0
            and verified_implementation_count == implementation_count
            and verified_tests_count == tests_count
        )
        capability["verification_status"] = "verified" if verified else "incomplete"
        capability["matching_eligibility"] = "eligible" if verified else "ineligible"
        return

    implementation_verified = (
        implementation_count > 0
        and verified_implementation_count == implementation_count
        and not audit["missing_paths"]
        and not audit["missing_symbols"]
    )
    test_failures = tests_count > 0 and verified_tests_count != tests_count
    capability["verification_status"] = "verified" if implementation_verified and not test_failures else "incomplete"
    capability["matching_eligibility"] = "limited" if implementation_verified else "ineligible"
    if tests_count == 0:
        audit["warnings"].append("partial capability has no test_evidence; matching is limited")


def _build_summary(capabilities: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": len(capabilities)}
    for key in ["eligible", "limited", "ineligible"]:
        summary[key] = sum(1 for item in capabilities if item.get("matching_eligibility") == key)
    for key in ["verified", "incomplete", "not_applicable"]:
        summary[key] = sum(1 for item in capabilities if item.get("verification_status") == key)
    return summary


def _append_counts(lines: list[str], title: str, counts: Counter[str]) -> None:
    lines.extend(["", f"## {title}", ""])
    if not counts:
        lines.append("- none: 0")
        return
    for key in sorted(counts):
        lines.append(f"- {key}: {counts[key]}")


def _bullet(items: list[Any]) -> str:
    if not items:
        return "- 없음"
    return "\n".join(f"- {item}" for item in items)


def _evidence_lines(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "- 없음"
    lines = []
    for entry in entries:
        lines.append(f"- `{entry['path']}`: {', '.join(entry.get('symbols', []))}")
    return "\n".join(lines)


def _audit_warning_lines(audit: dict[str, Any]) -> str:
    warnings = list(audit.get("warnings", []))
    for item in audit.get("missing_paths", []):
        warnings.append(f"missing path: {item}")
    for item in audit.get("missing_symbols", []):
        warnings.append(f"missing symbol: {item.get('path')}::{item.get('symbol')}")
    return _bullet(warnings)
