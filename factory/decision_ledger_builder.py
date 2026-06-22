from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import copy
import json

from factory.decision_model import (
    DECISION_INTAKE_ARTIFACT_TYPE,
    DECISION_LEDGER_ARTIFACT_TYPE,
    FOLLOW_UP_ACTIONS,
    SCHEMA_VERSION,
    DecisionModelError,
    build_subject_digest,
    canonical_json_digest,
    decision_revision,
    validate_decision_entry,
    validate_decision_intake,
    validate_decision_ledger,
)
from factory.requirement_capability_matcher import validate_capability_registry
from factory.requirement_model import (
    RequirementModelError,
    validate_match_artifact,
    validate_requirements_artifact,
)
from factory.utils import write_json, write_text


DECISION_REASON_CODES = [
    "active_must_gap",
    "pending_red",
    "conflicting_provenance",
    "red_not_modeled",
    "active_red_not_evaluated",
]


def load_decision_intake(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    intake_path = Path(path)
    try:
        data = json.loads(intake_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DecisionModelError(f"Malformed decision intake JSON: {exc}") from exc
    except OSError as exc:
        raise DecisionModelError(f"Could not read decision intake: {exc}") from exc
    if not isinstance(data, dict):
        raise DecisionModelError("Decision intake must be a JSON object")
    validate_decision_intake(data)
    return data


def build_decision_ledger(
    requirements: dict[str, Any],
    matches: dict[str, Any],
    capabilities: dict[str, Any],
    intake: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_input_artifacts(requirements, matches, capabilities)
    if intake is not None:
        validate_decision_intake(intake)

    requirements_by_id = {item["requirement_id"]: item for item in requirements["requirements"]}
    matches_by_id = {item["requirement_id"]: item for item in matches["matches"]}
    capability_ids = {item["capability_id"] for item in capabilities["capabilities"]}
    source_digests = {
        "contest_requirements": canonical_json_digest(requirements),
        "requirement_capability_match": canonical_json_digest(matches),
        "capability_registry": canonical_json_digest(capabilities),
    }
    warnings: list[str] = []
    if intake is not None:
        warnings.extend(_source_digest_warnings(source_digests, intake["source_digests"]))

    decisions_by_requirement = _decisions_by_requirement(
        intake,
        requirements_by_id=requirements_by_id,
        capability_ids=capability_ids,
    )

    records = []
    for requirement_id in sorted(requirements_by_id):
        requirement = requirements_by_id[requirement_id]
        match = matches_by_id[requirement_id]
        subject_digest = build_subject_digest(requirement, match)
        record = _build_record(
            requirement,
            match,
            subject_digest=subject_digest,
            decisions=decisions_by_requirement.get(requirement_id, []),
        )
        records.append(record)

    ledger = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": DECISION_LEDGER_ARTIFACT_TYPE,
        "source_artifacts": {
            "contest_requirements": "contest_requirements.json",
            "requirement_capability_match": "requirement_capability_match.json",
            "capability_registry": "capability_registry.json",
            "decision_intake": "decision_intake.json" if intake is not None else None,
        },
        "source_digests": source_digests,
        "summary": _summary(records),
        "records": records,
        "warnings": sorted(set(warnings)),
    }
    validate_decision_ledger(ledger)
    return ledger


def build_decision_intake_template(ledger: dict[str, Any]) -> dict[str, Any]:
    validate_decision_ledger(ledger)
    decisions = []
    warnings: list[str] = []
    for record in ledger["records"]:
        if not record["decision_required"] or record["resolution_status"] == "confirmed":
            continue
        leaves = [entry for entry in record["history"] if entry["is_leaf"]]
        if len(leaves) > 1:
            warnings.append(f"Manual conflict resolution is required for {record['requirement_id']}.")
            continue
        if leaves:
            current_id = leaves[0]["decision_id"]
            revision = decision_revision(current_id) + 1
            supersedes = current_id
        else:
            revision = 1
            supersedes = None
        stem = record["requirement_id"].removeprefix("req.")
        decisions.append(
            {
                "decision_id": f"dec.{stem}.r{revision:03d}",
                "requirement_id": record["requirement_id"],
                "expected_subject_digest": record["subject_digest"],
                "actor": "human",
                "decision_status": "pending",
                "action": "no_action",
                "decision_value": None,
                "rationale": "",
                "selected_capability_ids": [],
                "evidence_ids": list(record["evidence_ids"]),
                "conditions": [],
                "supersedes": supersedes,
                "notes": [],
            }
        )
    known_decision_ids = {
        item["decision_id"]
        for record in ledger["records"]
        for item in record["history"]
    }
    template = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": DECISION_INTAKE_ARTIFACT_TYPE,
        "source_digests": copy.deepcopy(ledger["source_digests"]),
        "decisions": sorted(decisions, key=lambda item: item["decision_id"]),
        "notes": sorted(warnings),
    }
    validate_decision_intake(template, known_decision_ids=known_decision_ids)
    return template


def render_decision_ledger_markdown(ledger: dict[str, Any]) -> str:
    validate_decision_ledger(ledger)
    summary = ledger["summary"]
    records = ledger["records"]
    lines = [
        "# Decision Ledger",
        "",
        "Decision Ledger는 requirement 및 capability match에 대한 사람/AI의 disposition 기록이다.",
        "confirmed decision은 Requirement, ContestSpec, Capability 또는 contest_overrides를 자동 변경하지 않는다.",
        "Decision Ledger가 완전하다는 사실은 Human Approval, solver 성능 또는 최종 제출 준비 완료를 뜻하지 않는다.",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "total",
        "decision_required",
        "not_required",
        "pending",
        "proposed",
        "confirmed",
        "rejected",
        "stale",
        "conflicting",
        "authoritative",
        "unresolved_required_count",
        "follow_up_required_count",
    ]:
        lines.append(f"- {key}: {summary[key]}")
    lines.extend(
        [
            "",
            "unresolved_required_count는 decision_required이면서 resolution_status가 confirmed가 아닌 record 수다.",
            "confirmed + wait_for_information은 decision은 내려졌으므로 unresolved에는 포함하지 않고 follow_up_required_count에 포함한다.",
            "",
        ]
    )

    _append_record_section(lines, "Decision Required", [r for r in records if r["decision_required"]])
    _append_record_section(
        lines,
        "Unresolved Required Decisions",
        [r for r in records if r["decision_required"] and r["resolution_status"] != "confirmed"],
    )
    _append_record_section(lines, "Stale Decisions", [r for r in records if r["resolution_status"] == "stale"])
    _append_record_section(lines, "Conflicting Decisions", [r for r in records if r["resolution_status"] == "conflicting"])
    _append_record_section(lines, "AI Proposals", [r for r in records if r["resolution_status"] == "proposed"])
    _append_record_section(lines, "Human Confirmed Decisions", [r for r in records if r["resolution_status"] == "confirmed"])
    _append_record_section(lines, "Rejected Proposals", [r for r in records if r["resolution_status"] == "rejected"])
    _append_record_section(lines, "Follow-up Required", [r for r in records if r["follow_up_required"]])
    _append_record_section(lines, "Not-required Records", [r for r in records if r["resolution_status"] == "not_required"])
    lines.extend(["", "## Warnings", "", _bullet(ledger["warnings"])])

    lines.extend(["", "## Record Details", ""])
    for record in records:
        lines.extend(
            [
                f"### {record['requirement_id']}",
                "",
                f"- title: {record['requirement_context']['title']}",
                f"- subject_digest: `{record['subject_digest']}`",
                f"- decision_required: {str(record['decision_required']).lower()}",
                f"- decision_required_reasons: {', '.join(record['decision_required_reasons']) or 'none'}",
                f"- resolution_status: {record['resolution_status']}",
                f"- authoritative: {str(record['authoritative']).lower()}",
                f"- current_decision_id: {record['current_decision_id'] or 'none'}",
                f"- current_action: {record['current_action'] or 'none'}",
                f"- follow_up_required: {str(record['follow_up_required']).lower()}",
                "",
                "#### History",
                "",
            ]
        )
        if not record["history"]:
            lines.append("- none")
        for item in record["history"]:
            lines.extend(
                [
                    f"- {item['decision_id']}",
                    f"  - actor: {item['actor']}",
                    f"  - decision_status: {item['decision_status']}",
                    f"  - action: {item['action']}",
                    f"  - supersedes: {item['supersedes'] or 'none'}",
                    f"  - digest_status: {item['digest_status']}",
                    f"  - is_leaf: {str(item['is_leaf']).lower()}",
                    f"  - semantic_status: {item['semantic_status']}",
                ]
            )
        if record["warnings"]:
            lines.extend(["", "#### Warnings", "", _bullet(record["warnings"])])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_decision_outputs(
    ledger: dict[str, Any],
    template: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    validate_decision_ledger(ledger)
    known_decision_ids = {
        item["decision_id"]
        for record in ledger["records"]
        for item in record["history"]
    }
    validate_decision_intake(template, known_decision_ids=known_decision_ids)
    out = Path(output_dir)
    return {
        "ledger_json": write_json(out / "decision_ledger.json", ledger),
        "ledger_md": write_text(out / "decision_ledger.md", render_decision_ledger_markdown(ledger)),
        "intake_template": write_json(out / "decision_intake_template.json", template),
    }


def _validate_input_artifacts(requirements: dict[str, Any], matches: dict[str, Any], capabilities: dict[str, Any]) -> None:
    try:
        validate_requirements_artifact(requirements)
        validate_match_artifact(matches, requirements["requirements"])
        validate_capability_registry(capabilities)
    except RequirementModelError as exc:
        raise DecisionModelError(str(exc)) from exc
    requirement_ids = [item["requirement_id"] for item in requirements["requirements"]]
    match_ids = [item["requirement_id"] for item in matches["matches"]]
    if requirement_ids != match_ids:
        raise DecisionModelError("Input Requirement/Match ID mismatch")


def _source_digest_warnings(current: dict[str, str], intake: dict[str, str]) -> list[str]:
    warnings = []
    for key in sorted(current):
        if current[key] != intake.get(key):
            warnings.append(f"Decision intake source digest mismatch for {key}.")
    return warnings


def _decisions_by_requirement(
    intake: dict[str, Any] | None,
    *,
    requirements_by_id: dict[str, dict[str, Any]],
    capability_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    if intake is None:
        return {}
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in intake["decisions"]:
        validate_decision_entry(entry)
        requirement_id = entry["requirement_id"]
        if requirement_id not in requirements_by_id:
            raise DecisionModelError(f"{entry['decision_id']} references unknown requirement_id {requirement_id}")
        unknown_caps = sorted(set(entry["selected_capability_ids"]) - capability_ids)
        if unknown_caps:
            raise DecisionModelError(f"{entry['decision_id']} selects unknown capability_id(s): {', '.join(unknown_caps)}")
        unknown_evidence = sorted(set(entry["evidence_ids"]) - set(requirements_by_id[requirement_id]["evidence_ids"]))
        if unknown_evidence:
            raise DecisionModelError(f"{entry['decision_id']} references unknown evidence_id(s): {', '.join(unknown_evidence)}")
        result[requirement_id].append(copy.deepcopy(entry))
    for requirement_id in result:
        result[requirement_id].sort(key=lambda item: (decision_revision(item["decision_id"]), item["decision_id"]))
    return result


def _build_record(
    requirement: dict[str, Any],
    match: dict[str, Any],
    *,
    subject_digest: str,
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    reasons = _decision_required_reasons(requirement, match)
    history = _history(decisions, subject_digest, match)
    leaves = [entry for entry in history if entry["is_leaf"]]
    warnings: list[str] = []
    resolution_status = _resolution_status(bool(reasons), leaves)
    if resolution_status == "conflicting":
        if len(leaves) > 1:
            warnings.append("Multiple unsuperseded leaf decisions exist.")
        if any(entry["semantic_status"] == "conflicting" for entry in leaves):
            warnings.append("Current decision has semantic conflict with current match.")

    current = leaves[0] if len(leaves) == 1 else None
    authoritative = bool(
        current
        and resolution_status == "confirmed"
        and current["actor"] == "human"
        and current["decision_status"] == "confirmed"
        and current["digest_status"] == "current"
        and current["semantic_status"] == "valid"
    )
    current_action = current["action"] if current is not None and resolution_status not in {"stale", "conflicting"} else None
    follow_up_required = bool(authoritative and current_action in FOLLOW_UP_ACTIONS)

    return {
        "requirement_id": requirement["requirement_id"],
        "subject_digest": subject_digest,
        "decision_required": bool(reasons),
        "decision_required_reasons": reasons,
        "requirement_context": {
            "title": requirement["title"],
            "origin": requirement["origin"],
            "domain": requirement["domain"],
            "requirement_type": requirement["requirement_type"],
            "priority": requirement["priority"],
            "provenance_status": requirement["provenance_status"],
            "applicability": requirement["applicability"],
            "risk_level": requirement["risk_level"],
            "required_tokens": sorted(set(requirement["required_tokens"])),
        },
        "match_context": {
            "match_status": match["match_status"],
            "matched_capability_ids": sorted(set(match["matched_capability_ids"])),
            "dependency_capability_ids": sorted(set(match["dependency_capability_ids"])),
            "missing_tokens": sorted(set(match["missing_tokens"])),
            "blocked_by": sorted(set(match["blocked_by"])),
        },
        "source_refs": _sorted_unique_objects(requirement["source_refs"]),
        "evidence_ids": sorted(set(requirement["evidence_ids"])),
        "resolution_status": resolution_status,
        "authoritative": authoritative,
        "current_decision_id": current["decision_id"] if current is not None else None,
        "current_action": current_action,
        "decision_value": current["decision_value"] if current is not None and resolution_status not in {"stale", "conflicting"} else None,
        "selected_capability_ids": (
            sorted(set(current["selected_capability_ids"]))
            if current is not None and resolution_status not in {"stale", "conflicting"}
            else []
        ),
        "follow_up_required": follow_up_required,
        "history": history,
        "warnings": sorted(set(warnings)),
    }


def _decision_required_reasons(requirement: dict[str, Any], match: dict[str, Any]) -> list[str]:
    reasons = []
    if (
        requirement["priority"] == "must"
        and requirement["applicability"] == "active"
        and match["match_status"] in {"partial", "unmet", "blocked"}
    ):
        reasons.append("active_must_gap")
    if requirement["risk_level"] == "red" and requirement["applicability"] == "pending":
        reasons.append("pending_red")
    if requirement["provenance_status"] == "conflicting":
        reasons.append("conflicting_provenance")
    if requirement["risk_level"] == "red" and requirement["applicability"] == "not_modeled":
        reasons.append("red_not_modeled")
    if (
        requirement["risk_level"] == "red"
        and requirement["applicability"] == "active"
        and match["match_status"] == "not_evaluated"
    ):
        reasons.append("active_red_not_evaluated")
    return [reason for reason in DECISION_REASON_CODES if reason in reasons]


def _history(decisions: list[dict[str, Any]], subject_digest: str, match: dict[str, Any]) -> list[dict[str, Any]]:
    superseded = {entry["supersedes"] for entry in decisions if entry["supersedes"] is not None}
    items = []
    matched_ids = set(match["matched_capability_ids"])
    for entry in decisions:
        item = copy.deepcopy(entry)
        item["evidence_ids"] = sorted(set(item["evidence_ids"]))
        item["selected_capability_ids"] = sorted(set(item["selected_capability_ids"]))
        item["conditions"] = sorted(set(item["conditions"]))
        item["notes"] = sorted(set(item["notes"]))
        item["digest_status"] = "current" if item["expected_subject_digest"] == subject_digest else "stale"
        item["is_leaf"] = item["decision_id"] not in superseded
        item["semantic_status"] = _semantic_status(item, matched_ids)
        items.append(item)
    return sorted(items, key=lambda item: (decision_revision(item["decision_id"]), item["decision_id"]))


def _semantic_status(entry: dict[str, Any], matched_ids: set[str]) -> str:
    if entry["action"] != "use_existing_capability":
        return "valid"
    selected = set(entry["selected_capability_ids"])
    return "valid" if selected and selected <= matched_ids else "conflicting"


def _resolution_status(decision_required: bool, leaves: list[dict[str, Any]]) -> str:
    if len(leaves) > 1 or any(entry["semantic_status"] == "conflicting" for entry in leaves):
        return "conflicting"
    if len(leaves) == 1 and leaves[0]["digest_status"] == "stale":
        return "stale"
    if not leaves:
        return "pending" if decision_required else "not_required"
    leaf = leaves[0]
    if leaf["decision_status"] == "pending":
        return "pending"
    if leaf["actor"] == "ai" and leaf["decision_status"] == "proposed":
        return "proposed"
    if leaf["actor"] == "human" and leaf["decision_status"] == "confirmed":
        return "confirmed"
    if leaf["actor"] == "human" and leaf["decision_status"] == "rejected":
        return "rejected"
    return "conflicting"


def _summary(records: list[dict[str, Any]]) -> dict[str, int]:
    statuses = Counter(record["resolution_status"] for record in records)
    return {
        "total": len(records),
        "decision_required": sum(1 for record in records if record["decision_required"]),
        "not_required": statuses["not_required"],
        "pending": statuses["pending"],
        "proposed": statuses["proposed"],
        "confirmed": statuses["confirmed"],
        "rejected": statuses["rejected"],
        "stale": statuses["stale"],
        "conflicting": statuses["conflicting"],
        "authoritative": sum(1 for record in records if record["authoritative"]),
        "unresolved_required_count": sum(
            1 for record in records if record["decision_required"] and record["resolution_status"] != "confirmed"
        ),
        "follow_up_required_count": sum(1 for record in records if record["follow_up_required"]),
    }


def _sorted_unique_objects(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {canonical_json_digest(item): item for item in items}
    return [keyed[key] for key in sorted(keyed)]


def _append_record_section(lines: list[str], title: str, records: list[dict[str, Any]]) -> None:
    lines.extend(["", f"## {title}", ""])
    if not records:
        lines.append("- none")
        return
    for record in records:
        reasons = f" ({', '.join(record['decision_required_reasons'])})" if record["decision_required_reasons"] else ""
        lines.append(f"- `{record['requirement_id']}`: {record['resolution_status']}{reasons}")


def _bullet(items: list[Any]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)
