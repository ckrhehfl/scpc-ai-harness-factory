from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import re
from typing import Any

from factory.contest_reader import read_simple_yaml
from factory.spec_builder import SUPPORTED_OVERRIDE_PATHS, iter_override_items, set_nested_value
from factory.utils import to_simple_yaml, write_json, write_text


MACHINE_PAYLOAD_HEADING = "## Machine-readable Analysis Payload"
REQUIRED_PAYLOAD_FIELDS = {"candidate_overrides", "code_agent_tasks", "human_decisions"}
EXPECTED_PAYLOAD_FIELDS = {
    "problem_type_candidates",
    "input_structure",
    "output_structure",
    "evaluation_metric_candidates",
    "rule_risks",
    "usage_candidates",
    "required_harness_modules",
    "solver_candidates",
    "human_decisions",
    "contest_spec_updates",
    "harness_blueprint_updates",
    "candidate_overrides",
    "code_agent_tasks",
}
ALLOWED_CONFIDENCE = {"high", "medium", "low", "unknown"}


class AnalysisIntakeError(ValueError):
    """Raised when an AI analysis response cannot be safely parsed."""


def extract_machine_payload(response_markdown: str) -> dict[str, Any]:
    heading_index = response_markdown.find(MACHINE_PAYLOAD_HEADING)
    if heading_index < 0:
        raise AnalysisIntakeError(f"Missing required heading: {MACHINE_PAYLOAD_HEADING}")

    after_heading = response_markdown[heading_index + len(MACHINE_PAYLOAD_HEADING):]
    match = re.search(r"```json\s*\n(.*?)\n```", after_heading, flags=re.DOTALL)
    if not match:
        raise AnalysisIntakeError("Missing json fenced code block after machine-readable payload heading.")

    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise AnalysisIntakeError(f"Malformed JSON payload: {exc.msg} at line {exc.lineno} column {exc.colno}.") from exc

    if not isinstance(payload, dict):
        raise AnalysisIntakeError("Machine-readable payload must be a JSON object.")

    missing = sorted(REQUIRED_PAYLOAD_FIELDS - set(payload))
    if missing:
        raise AnalysisIntakeError(f"Missing required payload field(s): {', '.join(missing)}")

    return payload


def build_parse_warnings(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    missing_optional = sorted(EXPECTED_PAYLOAD_FIELDS - REQUIRED_PAYLOAD_FIELDS - set(payload))
    for field in missing_optional:
        warnings.append(f"Optional payload field is missing: {field}")
    return warnings


def _is_excluded_value(value: Any) -> bool:
    return value is None or value == "" or value == "unknown"


def _flatten_existing_overrides(contest_path: str | Path) -> dict[str, Any]:
    overrides_path = Path(contest_path) / "contest_overrides.yaml"
    overrides = read_simple_yaml(overrides_path)
    return dict(iter_override_items(overrides))


def _path_counts(candidates: Any) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not isinstance(candidates, list):
        return counts
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        path = candidate.get("path")
        if isinstance(path, str) and path in SUPPORTED_OVERRIDE_PATHS:
            counts[path] += 1
    return counts


def classify_override_candidates(
    payload: dict[str, Any],
    contest_path: str | Path,
) -> dict[str, list[dict[str, Any]]]:
    raw_candidates = payload.get("candidate_overrides")
    if not isinstance(raw_candidates, list):
        raise AnalysisIntakeError("candidate_overrides must be a list.")

    existing_overrides = _flatten_existing_overrides(contest_path)
    duplicate_paths = {path for path, count in _path_counts(raw_candidates).items() if count > 1}

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    confirmed: list[dict[str, Any]] = []

    for index, candidate in enumerate(raw_candidates):
        if not isinstance(candidate, dict):
            rejected.append({"index": index, "candidate": candidate, "reason": "candidate_override must be an object"})
            continue

        path = candidate.get("path")
        value = candidate.get("value")
        confidence = candidate.get("confidence", "unknown")

        if not isinstance(path, str) or not path:
            rejected.append({**candidate, "index": index, "reason": "missing override path"})
            continue
        if path not in SUPPORTED_OVERRIDE_PATHS:
            rejected.append({**candidate, "index": index, "reason": "unsupported override path"})
            continue
        if confidence not in ALLOWED_CONFIDENCE:
            rejected.append({**candidate, "index": index, "reason": "unsupported confidence value"})
            continue
        if _is_excluded_value(value):
            rejected.append({**candidate, "index": index, "reason": "empty or unknown value"})
            continue
        if confidence in {"low", "unknown"}:
            rejected.append({**candidate, "index": index, "reason": "low or unknown confidence"})
            continue
        if path in duplicate_paths:
            conflicts.append({**candidate, "index": index, "reason": "duplicate candidate path"})
            continue
        if path in existing_overrides:
            existing_value = existing_overrides[path]
            if existing_value == value:
                confirmed.append({**candidate, "index": index, "existing_value": existing_value})
            else:
                conflicts.append({
                    **candidate,
                    "index": index,
                    "existing_value": existing_value,
                    "reason": "differs from existing contest_overrides.yaml",
                })
            continue

        accepted.append({**candidate, "index": index})

    return {
        "accepted_override_candidates": accepted,
        "rejected_override_candidates": rejected,
        "conflicting_override_candidates": conflicts,
        "already_confirmed_candidates": confirmed,
    }


def build_proposed_overrides(accepted_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    proposed: dict[str, Any] = {}
    for candidate in accepted_candidates:
        set_nested_value(proposed, candidate["path"], candidate["value"])
    return proposed


def render_code_agent_task_plan(tasks: Any) -> str:
    lines = ["# Code Agent Task Plan", ""]
    if not isinstance(tasks, list) or not tasks:
        lines.append("- 없음")
        return "\n".join(lines) + "\n"

    for index, task in enumerate(tasks, start=1):
        task = task if isinstance(task, dict) else {"title": str(task)}
        title = task.get("title") or f"Task {index}"
        priority = task.get("priority") or "unknown"
        files = task.get("files") if isinstance(task.get("files"), list) else []
        criteria = task.get("acceptance_criteria") if isinstance(task.get("acceptance_criteria"), list) else []
        lines.extend([
            f"## {index}. {title}",
            "",
            f"- priority: {priority}",
            "- files:",
        ])
        lines.extend([f"  - {file}" for file in files] or ["  - 없음"])
        lines.append("- acceptance criteria:")
        lines.extend([f"  - {item}" for item in criteria] or ["  - 없음"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_value(value: Any) -> str:
    if value is None or value == "":
        return "- 없음"
    if isinstance(value, (dict, list)):
        rendered = to_simple_yaml(value)
        return f"```yaml\n{rendered}\n```" if rendered else "- 없음"
    return str(value)


def _render_candidate_list(items: Any, empty: str = "- 없음") -> str:
    if not isinstance(items, list) or not items:
        return empty
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            label = item.get("value") or item.get("name") or item.get("item") or item.get("title") or item.get("path") or "candidate"
            details = []
            for key in ["confidence", "risk", "reason", "evidence", "status", "priority"]:
                if key in item:
                    details.append(f"{key}: {item[key]}")
            suffix = f" ({'; '.join(details)})" if details else ""
            lines.append(f"- {label}{suffix}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)


def _render_override_candidates(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- 없음"
    lines = []
    for item in items:
        reason = f" - {item.get('reason')}" if item.get("reason") else ""
        existing = f" (existing: {item.get('existing_value')})" if "existing_value" in item else ""
        lines.append(f"- `{item.get('path')}` = `{item.get('value')}` confidence={item.get('confidence')}{existing}{reason}")
    return "\n".join(lines)


def render_review_markdown(candidates: dict[str, Any]) -> str:
    payload = candidates["payload"]
    sections = [
        ("Status", "parsed" if candidates.get("parsed") else "parse_failed"),
        ("Source", f"- response: `{candidates['source_response_path']}`\n- contest: `{candidates['contest_path']}`"),
        ("Problem Type Candidates", _render_candidate_list(payload.get("problem_type_candidates"))),
        ("Input Structure", _render_value(payload.get("input_structure"))),
        ("Output Structure", _render_value(payload.get("output_structure"))),
        ("Evaluation Metric Candidates", _render_candidate_list(payload.get("evaluation_metric_candidates"))),
        ("Rule Risks", _render_candidate_list(payload.get("rule_risks"))),
        ("Usage Candidates", _render_value(payload.get("usage_candidates"))),
        ("Required Harness Modules", _render_candidate_list(payload.get("required_harness_modules"))),
        ("Solver Candidates", _render_candidate_list(payload.get("solver_candidates"))),
        ("Human Decisions", _render_candidate_list(payload.get("human_decisions"))),
        ("Candidate ContestSpec Updates", _render_value(payload.get("contest_spec_updates", []))),
        ("Candidate HarnessBlueprint Updates", _render_value(payload.get("harness_blueprint_updates", []))),
        ("Accepted Override Candidates", _render_override_candidates(candidates["accepted_override_candidates"])),
        ("Rejected Override Candidates", _render_override_candidates(candidates["rejected_override_candidates"])),
        ("Existing Override Conflicts", _render_override_candidates(candidates["conflicting_override_candidates"])),
        ("Already Confirmed", _render_override_candidates(candidates["already_confirmed_candidates"])),
        ("Code Agent Tasks", _render_candidate_list(payload.get("code_agent_tasks"))),
        ("Parse Warnings", "\n".join(f"- {warning}" for warning in candidates["parse_warnings"]) or "- 없음"),
        (
            "Human Approval Required",
            "이 보고서의 모든 내용은 후보이며 자동 확정되지 않는다.\n"
            "승인된 항목만 사람이 contest_overrides.yaml에 반영해야 한다.",
        ),
    ]

    lines = ["# AI Analysis Review", ""]
    for title, body in sections:
        lines.extend([f"## {title}", "", body, ""])
    return "\n".join(lines).rstrip() + "\n"


def build_analysis_candidates(
    *,
    response_path: str | Path,
    contest_path: str | Path,
) -> dict[str, Any]:
    response_file = Path(response_path)
    if not response_file.exists():
        raise AnalysisIntakeError(f"Analysis response file not found: {response_file}")
    contest_dir = Path(contest_path)
    if not contest_dir.exists():
        raise AnalysisIntakeError(f"Contest folder not found: {contest_dir}")

    payload = extract_machine_payload(response_file.read_text(encoding="utf-8"))
    parse_warnings = build_parse_warnings(payload)
    classified = classify_override_candidates(payload, contest_dir)
    return {
        "source_response_path": str(response_file),
        "contest_path": str(contest_dir),
        "parsed": True,
        "parse_warnings": parse_warnings,
        "payload": payload,
        **classified,
    }


def save_analysis_review_outputs(
    candidates: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    proposed = build_proposed_overrides(candidates["accepted_override_candidates"])
    proposed_yaml = to_simple_yaml(proposed) or "{}"

    paths = {
        "candidates_json": write_json(output_root / "ai_analysis_candidates.json", candidates),
        "review_md": write_text(output_root / "ai_analysis_review.md", render_review_markdown(candidates)),
        "proposed_yaml": write_text(output_root / "contest_overrides.proposed.yaml", proposed_yaml + "\n"),
        "task_plan_md": write_text(
            output_root / "code_agent_task_plan.md",
            render_code_agent_task_plan(candidates["payload"].get("code_agent_tasks")),
        ),
    }
    return paths


def run_analysis_review(
    *,
    contest_path: str | Path,
    response_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Path]:
    candidates = build_analysis_candidates(response_path=response_path, contest_path=contest_path)
    return save_analysis_review_outputs(candidates, output_dir)
