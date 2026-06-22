from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from factory.requirement_model import (
    MATCH_ARTIFACT_TYPE,
    SCHEMA_VERSION,
    RequirementModelError,
    build_match_summary,
    validate_match_artifact,
    validate_requirements_artifact,
)


PASSING_GATE_VALUES = {"true", "allowed", "confirmed", "yes"}
BLOCKING_GATE_VALUES = {"", "unknown", "false", "not_allowed", "disallowed", "no"}


def load_json(path: str | Path, label: str) -> dict[str, Any]:
    artifact_path = Path(path)
    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RequirementModelError(f"Malformed JSON in {label}: {exc}") from exc
    except OSError as exc:
        raise RequirementModelError(f"Could not read {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise RequirementModelError(f"{label} must be a JSON object")
    return data


def validate_capability_registry(registry: dict[str, Any]) -> None:
    if not isinstance(registry, dict):
        raise RequirementModelError("Capability registry must be an object")
    if registry.get("schema_version") != "v0.10A":
        raise RequirementModelError("Capability registry schema_version must be v0.10A")
    if registry.get("artifact_type") != "capability_registry":
        raise RequirementModelError("Capability registry artifact_type must be capability_registry")
    capabilities = registry.get("capabilities")
    if not isinstance(capabilities, list):
        raise RequirementModelError("Capability registry capabilities must be a list")
    ids = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            raise RequirementModelError("Capability entries must be objects")
        capability_id = capability.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
            raise RequirementModelError("Capability entry missing capability_id")
        ids.append(capability_id)
        if capability.get("matching_eligibility") not in {"eligible", "limited", "ineligible"}:
            raise RequirementModelError(f"{capability_id} has invalid matching_eligibility")
        for field in ["provides", "dependencies", "risk_gates"]:
            if not isinstance(capability.get(field), list):
                raise RequirementModelError(f"{capability_id}.{field} must be a list")
            for item in capability[field]:
                if not isinstance(item, str) or not item:
                    raise RequirementModelError(f"{capability_id}.{field} entries must be non-empty strings")
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise RequirementModelError(f"Duplicate capability_id(s): {', '.join(duplicates)}")


def match_requirements_to_capabilities(
    contest_requirements: dict[str, Any],
    capability_registry: dict[str, Any],
    contest_spec: dict[str, Any],
    *,
    source_requirements: str = "generated/contest_requirements.json",
    source_capabilities: str = "generated/capability_registry.json",
) -> dict[str, Any]:
    validate_requirements_artifact(contest_requirements)
    validate_capability_registry(capability_registry)
    if not isinstance(contest_spec, dict):
        raise RequirementModelError("contest_spec must be an object")

    capabilities = {item["capability_id"]: item for item in capability_registry["capabilities"]}
    evaluator = _CapabilityEvaluator(capabilities, contest_spec)
    token_index = _build_token_index(capability_registry["capabilities"])
    matches = []
    matched_tokens: set[str] = set()
    warnings: list[str] = []

    for requirement in contest_requirements["requirements"]:
        match = _match_requirement(requirement, token_index, evaluator)
        matches.append(match)
        for token_match in match["token_matches"]:
            if (
                token_match["eligible_capability_ids"]
                or token_match["limited_capability_ids"]
                or token_match["blocked_capability_ids"]
            ):
                matched_tokens.add(token_match["token"])
        warnings.extend(evaluator.warnings_for_requirement(requirement["requirement_id"]))

    matches.sort(key=lambda item: item["requirement_id"])
    required_tokens = {
        token
        for requirement in contest_requirements["requirements"]
        for token in requirement["required_tokens"]
    }
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": MATCH_ARTIFACT_TYPE,
        "source_requirements": source_requirements,
        "source_capabilities": source_capabilities,
        "summary": build_match_summary(contest_requirements["requirements"], matches),
        "matches": matches,
        "unmatched_tokens": sorted(required_tokens - matched_tokens),
        "warnings": sorted(set(warnings)),
    }
    validate_match_artifact(artifact, contest_requirements["requirements"])
    return artifact


def render_requirement_capability_match_markdown(artifact: dict[str, Any], requirements: list[dict[str, Any]]) -> str:
    validate_match_artifact(artifact, requirements)
    by_req = {item["requirement_id"]: item for item in requirements}
    summary = artifact["summary"]
    lines = [
        "# Requirement Capability Match",
        "",
        "Capability match는 현재 Registry의 token과 코드 근거를 비교한 기계적 결과다.",
        "공식 규칙 확인, solver 성능, Human Approval 또는 최종 제출 가능 여부를 보장하지 않는다.",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "total",
        "satisfied",
        "partial",
        "unmet",
        "blocked",
        "not_evaluated",
        "not_applicable",
        "active_must_gap_count",
        "pending_high_risk_count",
    ]:
        lines.append(f"- {key}: {summary[key]}")

    active_gaps = [
        match
        for match in artifact["matches"]
        if by_req[match["requirement_id"]]["priority"] == "must"
        and by_req[match["requirement_id"]]["applicability"] == "active"
        and match["match_status"] in {"partial", "unmet", "blocked"}
    ]
    pending_high = [
        req for req in requirements if req["risk_level"] == "red" and req["applicability"] == "pending"
    ]
    lines.extend(["", "## Active Must Gaps", "", _match_bullets(active_gaps)])
    lines.extend(["", "## Pending High-Risk Requirements", "", _requirement_bullets(pending_high)])

    for status, title in [
        ("satisfied", "Satisfied Requirements"),
        ("partial", "Partial Requirements"),
        ("unmet", "Unmet Requirements"),
        ("blocked", "Blocked Requirements"),
        ("not_evaluated", "Not-Evaluated Constraints"),
        ("not_applicable", "Not-Applicable Requirements"),
    ]:
        items = [match for match in artifact["matches"] if match["match_status"] == status]
        lines.extend(["", f"## {title}", "", _match_bullets(items)])

    lines.extend(["", "## Token Providers", ""])
    for match in artifact["matches"]:
        if not match["token_matches"]:
            continue
        lines.extend([f"### {match['requirement_id']}", ""])
        for token_match in match["token_matches"]:
            lines.extend(
                [
                    f"- token: `{token_match['token']}`",
                    f"  - eligible: {', '.join(token_match['eligible_capability_ids']) or 'none'}",
                    f"  - limited: {', '.join(token_match['limited_capability_ids']) or 'none'}",
                    f"  - ineligible: {', '.join(token_match['ineligible_capability_ids']) or 'none'}",
                    f"  - blocked: {', '.join(token_match['blocked_capability_ids']) or 'none'}",
                ]
            )
        lines.extend(
            [
                f"- dependencies: {', '.join(match['dependency_capability_ids']) or 'none'}",
                f"- blocked_by: {', '.join(match['blocked_by']) or 'none'}",
                "",
            ]
        )
    if artifact["warnings"]:
        lines.extend(["", "## Warnings", "", "\n".join(f"- {warning}" for warning in artifact["warnings"]), ""])
    return "\n".join(lines).rstrip() + "\n"


def _match_requirement(
    requirement: dict[str, Any],
    token_index: dict[str, list[dict[str, Any]]],
    evaluator: "_CapabilityEvaluator",
) -> dict[str, Any]:
    required_tokens = sorted(requirement["required_tokens"])
    token_matches = []
    matched_ids: set[str] = set()
    dependency_ids: set[str] = set()
    missing_tokens: list[str] = []
    blocked_by: set[str] = set()
    any_limited = False
    any_eligible = False
    all_tokens_matched = True
    any_provider_exists = False
    any_blocked_provider = False

    if requirement["requirement_type"] in {"constraint", "prohibition", "unresolved"}:
        status = "not_evaluated"
    elif requirement["applicability"] == "not_modeled":
        status = "not_applicable"
    elif requirement["applicability"] == "pending" or requirement["provenance_status"] == "conflicting":
        status = "blocked"
    else:
        status = ""

    for token in required_tokens:
        providers = token_index.get(token, [])
        if not providers:
            missing_tokens.append(token)
            all_tokens_matched = False
        eligible_ids: list[str] = []
        limited_ids: list[str] = []
        ineligible_ids: list[str] = []
        blocked_ids: list[str] = []
        for provider in providers:
            any_provider_exists = True
            result = evaluator.evaluate(provider["capability_id"])
            dependency_ids.update(result.dependencies)
            if result.status == "eligible":
                eligible_ids.append(provider["capability_id"])
                matched_ids.add(provider["capability_id"])
                any_eligible = True
            elif result.status == "limited":
                limited_ids.append(provider["capability_id"])
                matched_ids.add(provider["capability_id"])
                any_limited = True
            elif result.status == "ineligible":
                ineligible_ids.append(provider["capability_id"])
            else:
                blocked_ids.append(provider["capability_id"])
                any_blocked_provider = True
                blocked_by.update(result.reasons)
        if not (eligible_ids or limited_ids):
            all_tokens_matched = False
        token_matches.append(
            {
                "token": token,
                "eligible_capability_ids": sorted(set(eligible_ids)),
                "limited_capability_ids": sorted(set(limited_ids)),
                "ineligible_capability_ids": sorted(set(ineligible_ids)),
                "blocked_capability_ids": sorted(set(blocked_ids)),
            }
        )

    if not status:
        if all_tokens_matched and not any_limited and not any_blocked_provider:
            status = "satisfied"
        elif any_eligible or any_limited:
            status = "partial" if (any_limited or missing_tokens or not all_tokens_matched) else "satisfied"
        elif any_provider_exists and any_blocked_provider:
            status = "blocked"
        else:
            status = "unmet"

    return {
        "requirement_id": requirement["requirement_id"],
        "match_status": status,
        "required_tokens": required_tokens,
        "token_matches": token_matches,
        "matched_capability_ids": sorted(matched_ids),
        "dependency_capability_ids": sorted(dependency_ids),
        "missing_tokens": sorted(missing_tokens),
        "blocked_by": sorted(blocked_by),
        "notes": _match_notes(requirement, status),
    }


def _match_notes(requirement: dict[str, Any], status: str) -> list[str]:
    notes = list(requirement.get("notes", []))
    if requirement["requirement_type"] in {"constraint", "prohibition", "unresolved"}:
        notes.append("Capability token matching cannot prove compliance with this requirement type.")
    if status == "unmet" and requirement["requirement_id"] == "req.solver.task_solution":
        notes.append("Constant baseline capability is intentionally not treated as a task-specific solver.")
    return sorted(set(notes))


def _build_token_index(capabilities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for capability in capabilities:
        for token in capability.get("provides", []):
            index.setdefault(token, []).append(capability)
    for providers in index.values():
        providers.sort(key=lambda item: item["capability_id"])
    return index


class _CapabilityResult:
    def __init__(self, status: str, dependencies: set[str] | None = None, reasons: set[str] | None = None) -> None:
        self.status = status
        self.dependencies = dependencies or set()
        self.reasons = reasons or set()


class _CapabilityEvaluator:
    def __init__(self, capabilities: dict[str, dict[str, Any]], contest_spec: dict[str, Any]) -> None:
        self.capabilities = capabilities
        self.contest_spec = contest_spec
        self.cache: dict[str, _CapabilityResult] = {}
        self.requirement_warnings: dict[str, list[str]] = {}

    def evaluate(self, capability_id: str) -> _CapabilityResult:
        return self._evaluate(capability_id, [])

    def warnings_for_requirement(self, requirement_id: str) -> list[str]:
        return self.requirement_warnings.get(requirement_id, [])

    def _evaluate(self, capability_id: str, stack: list[str]) -> _CapabilityResult:
        if capability_id in self.cache:
            return self.cache[capability_id]
        if capability_id in stack:
            cycle = " -> ".join(stack + [capability_id])
            return _CapabilityResult("blocked", set(stack), {f"dependency cycle: {cycle}"})
        capability = self.capabilities.get(capability_id)
        if not capability:
            return _CapabilityResult("blocked", set(), {f"missing dependency capability: {capability_id}"})

        base = capability["matching_eligibility"]
        dependencies: set[str] = set()
        reasons: set[str] = set()
        if base == "ineligible":
            reasons.add(f"{capability_id} is ineligible")
            result = _CapabilityResult("ineligible", dependencies, reasons)
            self.cache[capability_id] = result
            return result

        status = "eligible" if base == "eligible" else "limited"
        for gate in capability.get("risk_gates", []):
            passed, value = _risk_gate_passes(self.contest_spec, gate)
            if not passed:
                status = "blocked"
                reasons.add(f"{capability_id} risk gate blocked: {gate}={value!r}")

        for dependency_id in capability.get("dependencies", []):
            dependencies.add(dependency_id)
            dependency = self._evaluate(dependency_id, stack + [capability_id])
            dependencies.update(dependency.dependencies)
            if dependency.status == "limited" and status == "eligible":
                status = "limited"
            if dependency.status in {"blocked", "ineligible"}:
                status = "blocked"
                reasons.add(f"{capability_id} dependency blocked: {dependency_id}")
                reasons.update(dependency.reasons)
        result = _CapabilityResult(status, dependencies, reasons)
        self.cache[capability_id] = result
        return result


def _risk_gate_passes(spec: dict[str, Any], dotted_path: str) -> tuple[bool, Any]:
    exists, value = _get_path(spec, dotted_path)
    if not exists or value is None:
        return False, None
    if isinstance(value, bool):
        return value, value
    text = str(value).strip().lower()
    if text in PASSING_GATE_VALUES:
        return True, value
    if text in BLOCKING_GATE_VALUES:
        return False, value
    return False, value


def _get_path(data: dict[str, Any], dotted_path: str) -> tuple[bool, Any]:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _match_bullets(matches: list[dict[str, Any]]) -> str:
    if not matches:
        return "- none"
    return "\n".join(f"- `{match['requirement_id']}`: {match['match_status']}" for match in matches)


def _requirement_bullets(requirements: list[dict[str, Any]]) -> str:
    if not requirements:
        return "- none"
    return "\n".join(f"- `{req['requirement_id']}`: {req['provenance_status']} / {req['risk_level']}" for req in requirements)
