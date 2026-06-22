from __future__ import annotations

from pathlib import Path
from typing import Any
import copy
import json

from factory.approval_model import (
    APPROVAL_INTAKE_ARTIFACT_TYPE,
    APPROVAL_SCOPE,
    APPROVAL_SUMMARY_ARTIFACT_TYPE,
    SCHEMA_VERSION,
    ApprovalModelError,
    approval_revision,
    build_readiness_digest,
    validate_approval_intake,
    validate_human_approval_summary,
)
from factory.decision_model import build_subject_digest, canonical_json_digest, validate_decision_ledger
from factory.requirement_capability_matcher import validate_capability_registry
from factory.requirement_model import RequirementModelError, validate_match_artifact, validate_requirements_artifact
from factory.utils import write_json, write_text


SOURCE_DIGEST_KEYS = [
    "contest_requirements",
    "requirement_capability_match",
    "decision_ledger",
    "capability_registry",
    "validation_report",
]
FOLLOW_UP_ACTIONS = {"implement_missing_capability", "confirm_value", "wait_for_information"}


def load_human_approval_intake(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    intake_path = Path(path)
    try:
        data = json.loads(intake_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ApprovalModelError(f"Malformed human approval intake JSON: {exc}") from exc
    except OSError as exc:
        raise ApprovalModelError(f"Could not read human approval intake: {exc}") from exc
    if not isinstance(data, dict):
        raise ApprovalModelError("Human approval intake must be a JSON object")
    validate_approval_intake(data)
    return data


def load_validation_report(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    report_path = Path(path)
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ApprovalModelError(f"Malformed validation report JSON: {exc}") from exc
    except OSError as exc:
        raise ApprovalModelError(f"Could not read validation report: {exc}") from exc
    if not isinstance(data, dict):
        raise ApprovalModelError("Validation report must be a JSON object")
    _validate_validation_report(data)
    return data


def build_human_approval_summary(
    requirements: dict[str, Any],
    matches: dict[str, Any],
    decision_ledger: dict[str, Any],
    capabilities: dict[str, Any],
    *,
    validation_report: dict[str, Any] | None = None,
    approval_intake: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_input_artifacts(requirements, matches, decision_ledger, capabilities)
    if validation_report is not None:
        _validate_validation_report(validation_report)
    if approval_intake is not None:
        validate_approval_intake(approval_intake)

    source_digests = {
        "contest_requirements": canonical_json_digest(requirements),
        "requirement_capability_match": canonical_json_digest(matches),
        "decision_ledger": canonical_json_digest(decision_ledger),
        "capability_registry": canonical_json_digest(capabilities),
        "validation_report": canonical_json_digest(validation_report) if validation_report is not None else None,
    }
    validation_summary = _validation_summary(validation_report)
    checks = _machine_checks(requirements, matches, decision_ledger, capabilities, source_digests, validation_summary)
    machine_readiness = _machine_readiness(checks)
    readiness_digest = build_readiness_digest(source_digests, machine_readiness)
    human_approval = _human_approval_state(approval_intake, readiness_digest, source_digests)
    overall_gate = _overall_gate(machine_readiness, human_approval)
    warnings = _summary_warnings(machine_readiness, human_approval, approval_intake, source_digests)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": APPROVAL_SUMMARY_ARTIFACT_TYPE,
        "scope": APPROVAL_SCOPE,
        "source_artifacts": {
            "contest_requirements": "contest_requirements.json",
            "requirement_capability_match": "requirement_capability_match.json",
            "decision_ledger": "decision_ledger.json",
            "capability_registry": "capability_registry.json",
            "validation_report": "validation_report.json" if validation_report is not None else None,
            "human_approval_intake": "human_approval_intake.json" if approval_intake is not None else None,
        },
        "source_digests": source_digests,
        "readiness_digest": readiness_digest,
        "machine_readiness": machine_readiness,
        "human_approval": human_approval,
        "overall_gate": overall_gate,
        "risk_summary": _risk_summary(requirements, matches),
        "validation_summary": validation_summary,
        "warnings": warnings,
    }
    validate_human_approval_summary(summary)
    return summary


def build_human_approval_intake_template(summary: dict[str, Any]) -> dict[str, Any]:
    validate_human_approval_summary(summary)
    approvals = []
    notes: list[str] = []
    human = summary["human_approval"]
    if summary["machine_readiness"]["status"] == "blocked":
        notes.append("Machine readiness is blocked; human approval cannot be requested yet.")
    elif human["status"] == "conflicting":
        notes.append("Manual approval conflict resolution is required.")
    elif human["status"] in {"approved", "rejected"} and human["authoritative"]:
        approvals = []
    else:
        leaf = _single_leaf(human["history"])
        supersedes = leaf["approval_id"] if leaf and human["status"] in {"pending", "stale", "conditional"} else None
        revision = approval_revision(supersedes) + 1 if supersedes else 1
        approvals.append(
            {
                "approval_id": f"approval.local_submission_candidate.r{revision:03d}",
                "scope": APPROVAL_SCOPE,
                "expected_readiness_digest": summary["readiness_digest"],
                "actor": "human",
                "approval_status": "pending",
                "rationale": "",
                "conditions": [],
                "supersedes": supersedes,
                "notes": [],
            }
        )
    template = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": APPROVAL_INTAKE_ARTIFACT_TYPE,
        "source_digests": copy.deepcopy(summary["source_digests"]),
        "readiness_digest": summary["readiness_digest"],
        "approvals": approvals,
        "notes": sorted(set(notes)),
    }
    known_ids = {item["approval_id"] for item in human["history"]}
    validate_approval_intake(template, known_approval_ids=known_ids)
    return template


def render_human_approval_summary_markdown(summary: dict[str, Any]) -> str:
    validate_human_approval_summary(summary)
    lines = [
        "# Human Approval Summary",
        "",
        "이 문서는 local_submission_candidate에 대한 기계적 readiness와 명시적 Human Approval을 요약한다.",
        "approved는 현재 로컬 artifact가 구성된 Gate를 통과했다는 뜻이며,",
        "공식 대회 규칙 확인, solver 성능, 리더보드 점수 또는 실제 제출 성공을 보장하지 않는다.",
        "Human Approval은 blocker를 덮어쓰지 않는다.",
        "",
        "## Overall Gate",
        "",
        f"- status: {summary['overall_gate']['status']}",
        f"- exit_code: {summary['overall_gate']['exit_code']}",
        f"- statement: {summary['overall_gate']['statement']}",
        "",
        "## Machine Readiness",
        "",
        f"- status: {summary['machine_readiness']['status']}",
        f"- blocker_count: {summary['machine_readiness']['blocker_count']}",
        f"- warning_count: {summary['machine_readiness']['warning_count']}",
        "",
        "## Blocking Checks",
        "",
        _checks_lines([c for c in summary["machine_readiness"]["checks"] if c["severity"] == "blocker" and c["status"] == "fail"]),
        "",
        "## Warnings",
        "",
        _bullet(summary["warnings"] + [c["check_id"] for c in summary["machine_readiness"]["checks"] if c["status"] == "warning"]),
        "",
        "## Decision State",
        "",
    ]
    for key in ["gate.decisions.unresolved_required", "gate.decisions.stale", "gate.decisions.conflicting", "gate.decisions.follow_up_required"]:
        check = _check_by_id(summary, key)
        lines.append(f"- {key}: {check['status']} ({check['observed']}/{check['expected']})")
    lines.extend(["", "## Risk Summary", ""])
    for key, value in summary["risk_summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Required Capability Health", ""])
    lines.append(_checks_lines([_check_by_id(summary, "gate.capabilities.required_health")]))
    lines.extend(["", "## Validation Summary", ""])
    for key, value in summary["validation_summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Human Approval",
            "",
            f"- status: {summary['human_approval']['status']}",
            f"- authoritative: {str(summary['human_approval']['authoritative']).lower()}",
            f"- approval_granted: {str(summary['human_approval']['approval_granted']).lower()}",
            f"- current_approval_id: {summary['human_approval']['current_approval_id'] or 'none'}",
            "",
            "## Approval History",
            "",
        ]
    )
    if not summary["human_approval"]["history"]:
        lines.append("- none")
    for item in summary["human_approval"]["history"]:
        lines.extend(
            [
                f"- {item['approval_id']}",
                f"  - status: {item['approval_status']}",
                f"  - digest_status: {item['digest_status']}",
                f"  - is_leaf: {str(item['is_leaf']).lower()}",
                f"  - supersedes: {item['supersedes'] or 'none'}",
            ]
        )
    lines.extend(["", "## Remaining Actions", ""])
    blockers = summary["overall_gate"]["blocking_check_ids"]
    if blockers:
        lines.append(_bullet(blockers))
    elif summary["overall_gate"]["status"] == "awaiting_human_approval":
        lines.append("- Provide explicit human approval for the current readiness digest.")
    else:
        lines.append("- none")
    lines.extend(["", "## Source Digests", ""])
    for key in SOURCE_DIGEST_KEYS:
        lines.append(f"- {key}: `{summary['source_digests'][key]}`")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- approved는 local gate만 의미한다.",
            "- 공식 규칙 확인, solver quality, 법률/IP 검토, 온라인 제출 성공을 보장하지 않는다.",
            "- Human Approval은 machine readiness blocker를 덮어쓸 수 없다.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def save_human_approval_outputs(
    summary: dict[str, Any],
    template: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    validate_human_approval_summary(summary)
    validate_approval_intake(template, known_approval_ids={item["approval_id"] for item in summary["human_approval"]["history"]})
    out = Path(output_dir)
    return {
        "summary_json": write_json(out / "human_approval_summary.json", summary),
        "summary_md": write_text(out / "human_approval_summary.md", render_human_approval_summary_markdown(summary)),
        "approval_template": write_json(out / "human_approval_intake_template.json", template),
    }


def _validate_input_artifacts(
    requirements: dict[str, Any],
    matches: dict[str, Any],
    decision_ledger: dict[str, Any],
    capabilities: dict[str, Any],
) -> None:
    try:
        validate_requirements_artifact(requirements)
        validate_match_artifact(matches, requirements["requirements"])
        validate_decision_ledger(decision_ledger)
        validate_capability_registry(capabilities)
    except (RequirementModelError, ValueError) as exc:
        raise ApprovalModelError(str(exc)) from exc
    requirement_ids = [item["requirement_id"] for item in requirements["requirements"]]
    match_ids = [item["requirement_id"] for item in matches["matches"]]
    ledger_ids = [item["requirement_id"] for item in decision_ledger["records"]]
    if requirement_ids != match_ids or requirement_ids != ledger_ids:
        raise ApprovalModelError("Requirement IDs must match across requirements, matches, and decision ledger")


def _validate_validation_report(report: dict[str, Any]) -> None:
    if not isinstance(report.get("passed"), bool):
        raise ApprovalModelError("validation_report.passed must be a bool")
    for field in ["error_count", "warning_count"]:
        if not isinstance(report.get(field), int) or report[field] < 0:
            raise ApprovalModelError(f"validation_report.{field} must be a non-negative int")
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise ApprovalModelError("validation_report.checks must be a list")
    failed_errors = 0
    failed_warnings = 0
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise ApprovalModelError(f"validation_report.checks[{index}] must be an object")
        if not isinstance(check.get("name"), str) or not check["name"].strip():
            raise ApprovalModelError(f"validation_report.checks[{index}].name must be a non-empty string")
        if not isinstance(check.get("passed"), bool):
            raise ApprovalModelError(f"validation_report.checks[{index}].passed must be a bool")
        if check.get("severity") not in {"error", "warning"}:
            raise ApprovalModelError(f"validation_report.checks[{index}].severity must be error or warning")
        if not isinstance(check.get("message"), str):
            raise ApprovalModelError(f"validation_report.checks[{index}].message must be a string")
        if not isinstance(check.get("details"), dict):
            raise ApprovalModelError(f"validation_report.checks[{index}].details must be an object")
        if not check["passed"] and check["severity"] == "error":
            failed_errors += 1
        if not check["passed"] and check["severity"] == "warning":
            failed_warnings += 1
    if report["error_count"] != failed_errors:
        raise ApprovalModelError("validation_report.error_count does not match failed error checks")
    if report["warning_count"] != failed_warnings:
        raise ApprovalModelError("validation_report.warning_count does not match failed warning checks")
    if report["passed"] != (failed_errors == 0):
        raise ApprovalModelError("validation_report.passed does not match error_count")


def _machine_checks(
    requirements: dict[str, Any],
    matches: dict[str, Any],
    ledger: dict[str, Any],
    capabilities: dict[str, Any],
    source_digests: dict[str, str | None],
    validation_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    req_by_id = {item["requirement_id"]: item for item in requirements["requirements"]}
    match_by_id = {item["requirement_id"]: item for item in matches["matches"]}
    caps_by_id = {item["capability_id"]: item for item in capabilities["capabilities"]}
    records_by_id = {item["requirement_id"]: item for item in ledger["records"]}

    active_gap_ids = sorted(
        requirement_id
        for requirement_id, requirement in req_by_id.items()
        if requirement["priority"] == "must"
        and requirement["applicability"] == "active"
        and match_by_id[requirement_id]["match_status"] in {"partial", "unmet", "blocked"}
    )
    checks = [
        _check(
            "gate.requirements.active_must_gaps",
            "requirement",
            len(active_gap_ids) == 0,
            len(active_gap_ids),
            0,
            related_requirement_ids=active_gap_ids,
            notes=["Human decisions cannot waive active must capability gaps."] if active_gap_ids else [],
        )
    ]
    for check_id, key in [
        ("gate.decisions.unresolved_required", "unresolved_required_count"),
        ("gate.decisions.stale", "stale"),
        ("gate.decisions.conflicting", "conflicting"),
        ("gate.decisions.follow_up_required", "follow_up_required_count"),
    ]:
        observed = ledger["summary"][key]
        notes = []
        if key == "follow_up_required_count":
            notes.append("Confirmed implement_missing_capability, confirm_value, and wait_for_information remain blockers.")
        checks.append(_check(check_id, "decision", observed == 0, observed, 0, notes=notes))

    ledger_source_expected = {
        "contest_requirements": source_digests["contest_requirements"],
        "requirement_capability_match": source_digests["requirement_capability_match"],
        "capability_registry": source_digests["capability_registry"],
    }
    source_mismatches = sorted(
        key for key, digest in ledger_source_expected.items() if ledger["source_digests"].get(key) != digest
    )
    checks.append(
        _check(
            "gate.ledger.source_digests_current",
            "ledger",
            not source_mismatches,
            len(source_mismatches),
            0,
            notes=[f"Ledger source digest mismatch: {key}" for key in source_mismatches],
        )
    )
    stale_subjects = sorted(
        requirement_id
        for requirement_id, record in records_by_id.items()
        if record["subject_digest"] != build_subject_digest(req_by_id[requirement_id], match_by_id[requirement_id])
    )
    checks.append(
        _check(
            "gate.ledger.subjects_current",
            "ledger",
            not stale_subjects,
            len(stale_subjects),
            0,
            related_requirement_ids=stale_subjects,
        )
    )

    required_capability_ids = _required_capability_ids(req_by_id, match_by_id, ledger)
    unhealthy = sorted(
        capability_id
        for capability_id in required_capability_ids
        if capability_id not in caps_by_id
        or caps_by_id[capability_id].get("verification_status") != "verified"
        or caps_by_id[capability_id].get("matching_eligibility") != "eligible"
    )
    checks.append(
        _check(
            "gate.capabilities.required_health",
            "capability",
            not unhealthy,
            len(unhealthy),
            0,
            related_capability_ids=unhealthy,
            notes=["Required capabilities must exist, be verified, and be eligible."] if unhealthy else [],
        )
    )
    checks.append(_check("gate.validation.present", "validation", validation_summary["present"], int(not validation_summary["present"]), 0))
    checks.append(
        _check(
            "gate.validation.passed",
            "validation",
            validation_summary["present"] and validation_summary["passed"] and validation_summary["error_count"] == 0,
            validation_summary["error_count"] if validation_summary["present"] else 1,
            0,
            notes=["Validation pass does not prove solver accuracy or contest acceptance."],
        )
    )
    if validation_summary["present"] and validation_summary["warning_count"] > 0:
        checks.append(
            _check(
                "gate.validation.warnings",
                "validation",
                False,
                validation_summary["warning_count"],
                0,
                status="warning",
                severity="warning",
                notes=["Validation report contains warning check failures."],
            )
        )
    return sorted(checks, key=lambda item: item["check_id"])


def _required_capability_ids(
    requirements_by_id: dict[str, dict[str, Any]],
    matches_by_id: dict[str, dict[str, Any]],
    ledger: dict[str, Any],
) -> set[str]:
    capability_ids: set[str] = set()
    for requirement_id, requirement in requirements_by_id.items():
        match = matches_by_id[requirement_id]
        if requirement["priority"] == "must" and requirement["applicability"] == "active" and match["match_status"] == "satisfied":
            capability_ids.update(match["matched_capability_ids"])
            capability_ids.update(match["dependency_capability_ids"])
    for record in ledger["records"]:
        if record["authoritative"] and record["current_action"] == "use_existing_capability":
            capability_ids.update(record["selected_capability_ids"])
    return capability_ids


def _machine_readiness(checks: list[dict[str, Any]]) -> dict[str, Any]:
    blocker_count = sum(1 for check in checks if check["severity"] == "blocker" and check["status"] == "fail")
    warning_count = sum(1 for check in checks if check["status"] == "warning" or check["severity"] == "warning")
    return {
        "status": "blocked" if blocker_count else "reviewable",
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "checks": checks,
    }


def _human_approval_state(
    intake: dict[str, Any] | None,
    readiness_digest: str,
    source_digests: dict[str, str | None],
) -> dict[str, Any]:
    if intake is None:
        return {
            "status": "not_provided",
            "authoritative": False,
            "approval_granted": False,
            "current_approval_id": None,
            "history": [],
            "warnings": [],
        }
    superseded = {entry["supersedes"] for entry in intake["approvals"] if entry["supersedes"] is not None}
    history = []
    for entry in intake["approvals"]:
        item = copy.deepcopy(entry)
        item["conditions"] = sorted(set(item["conditions"]))
        item["notes"] = sorted(set(item["notes"]))
        item["digest_status"] = "current" if item["expected_readiness_digest"] == readiness_digest else "stale"
        item["is_leaf"] = item["approval_id"] not in superseded
        history.append(item)
    history.sort(key=lambda item: (approval_revision(item["approval_id"]), item["approval_id"]))
    leaves = [item for item in history if item["is_leaf"]]
    warnings = _source_digest_warnings(source_digests, intake["source_digests"])
    if len(leaves) > 1:
        status = "conflicting"
        current = None
        authoritative = False
    elif not leaves:
        status = "not_provided"
        current = None
        authoritative = False
    else:
        current = leaves[0]
        if current["digest_status"] == "stale":
            status = "stale"
            authoritative = False
        elif current["approval_status"] == "pending":
            status = "pending"
            authoritative = False
        else:
            status = current["approval_status"]
            authoritative = current["actor"] == "human"
    approval_granted = bool(authoritative and current is not None and current["approval_status"] == "approved")
    return {
        "status": status,
        "authoritative": authoritative,
        "approval_granted": approval_granted,
        "current_approval_id": current["approval_id"] if current is not None else None,
        "history": history,
        "warnings": sorted(set(warnings)),
    }


def _overall_gate(machine: dict[str, Any], human: dict[str, Any]) -> dict[str, Any]:
    blocking_ids = sorted(
        check["check_id"] for check in machine["checks"] if check["severity"] == "blocker" and check["status"] == "fail"
    )
    if human["status"] == "conflicting":
        status = "conflicting_approval"
    elif human["status"] == "stale":
        status = "stale_approval"
    elif human["authoritative"] and human["status"] == "rejected":
        status = "rejected"
    elif machine["status"] == "blocked":
        status = "blocked"
    elif human["authoritative"] and human["status"] == "conditional":
        status = "conditional_approval"
    elif machine["status"] == "reviewable" and human["approval_granted"]:
        status = "approved"
    else:
        status = "awaiting_human_approval"
    return {
        "status": status,
        "exit_code": 0 if status == "approved" else 2,
        "blocking_check_ids": blocking_ids,
        "statement": _gate_statement(status),
    }


def _validation_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "present": False,
            "passed": False,
            "error_count": 0,
            "warning_count": 0,
            "failed_error_check_names": [],
            "failed_warning_check_names": [],
        }
    failed_errors = sorted(check["name"] for check in report["checks"] if not check["passed"] and check["severity"] == "error")
    failed_warnings = sorted(check["name"] for check in report["checks"] if not check["passed"] and check["severity"] == "warning")
    return {
        "present": True,
        "passed": report["passed"],
        "error_count": report["error_count"],
        "warning_count": report["warning_count"],
        "failed_error_check_names": failed_errors,
        "failed_warning_check_names": failed_warnings,
    }


def _risk_summary(requirements: dict[str, Any], matches: dict[str, Any]) -> dict[str, int]:
    items = requirements["requirements"]
    matches_by_id = {item["requirement_id"]: item for item in matches["matches"]}
    return {
        "pending_red_count": sum(1 for item in items if item["risk_level"] == "red" and item["applicability"] == "pending"),
        "red_not_modeled_count": sum(1 for item in items if item["risk_level"] == "red" and item["applicability"] == "not_modeled"),
        "active_red_not_evaluated_count": sum(
            1
            for item in items
            if item["risk_level"] == "red"
            and item["applicability"] == "active"
            and matches_by_id[item["requirement_id"]]["match_status"] == "not_evaluated"
        ),
    }


def _summary_warnings(
    machine: dict[str, Any],
    human: dict[str, Any],
    intake: dict[str, Any] | None,
    source_digests: dict[str, str | None],
) -> list[str]:
    warnings = list(human["warnings"])
    if machine["status"] == "blocked" and human["approval_granted"]:
        warnings.append("Human approval cannot override machine readiness blockers.")
    if intake is not None:
        warnings.extend(_source_digest_warnings(source_digests, intake["source_digests"]))
    return sorted(set(warnings))


def _source_digest_warnings(current: dict[str, str | None], recorded: dict[str, str | None]) -> list[str]:
    return [
        f"Human approval intake source digest mismatch for {key}."
        for key in SOURCE_DIGEST_KEYS
        if recorded.get(key) != current.get(key)
    ]


def _check(
    check_id: str,
    category: str,
    passed: bool,
    observed: Any,
    expected: Any,
    *,
    related_requirement_ids: list[str] | None = None,
    related_capability_ids: list[str] | None = None,
    notes: list[str] | None = None,
    status: str | None = None,
    severity: str = "blocker",
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "category": category,
        "status": status or ("pass" if passed else "fail"),
        "severity": severity,
        "observed": observed,
        "expected": expected,
        "related_requirement_ids": sorted(set(related_requirement_ids or [])),
        "related_capability_ids": sorted(set(related_capability_ids or [])),
        "notes": sorted(set(notes or [])),
    }


def _check_by_id(summary: dict[str, Any], check_id: str) -> dict[str, Any]:
    return {item["check_id"]: item for item in summary["machine_readiness"]["checks"]}[check_id]


def _checks_lines(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return "- none"
    lines = []
    for check in checks:
        lines.append(f"- {check['check_id']}: {check['status']} observed={check['observed']} expected={check['expected']}")
    return "\n".join(lines)


def _single_leaf(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    leaves = [item for item in history if item["is_leaf"]]
    return leaves[0] if len(leaves) == 1 else None


def _gate_statement(status: str) -> str:
    statements = {
        "blocked": "Machine readiness has one or more blockers.",
        "awaiting_human_approval": "Machine readiness is reviewable and awaits explicit human approval.",
        "approved": "Current local artifacts passed the configured gate and have current human approval.",
        "rejected": "A current human rejection exists for this local submission candidate.",
        "conditional_approval": "A current conditional human approval exists but is not approval_granted.",
        "stale_approval": "The current approval leaf references a stale readiness digest.",
        "conflicting_approval": "Multiple unsuperseded approval leaves exist.",
    }
    return statements[status]


def _bullet(items: list[Any]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)
