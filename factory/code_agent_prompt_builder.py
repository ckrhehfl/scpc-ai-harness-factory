from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
import json
import re

from factory.utils import to_simple_yaml, write_json, write_text


VERSION = "v0.8"
PROMPT_FILENAME = "code_agent_implementation_prompt.md"
CONTEXT_FILENAME = "code_agent_context.json"
REQUIRED_OUTPUT_FILES = [
    "contest_spec.json",
    "gap_report.md",
    "harness_blueprint.md",
    "code_agent_task_plan.md",
]
OPTIONAL_OUTPUT_FILES = ["ai_analysis_review.md"]
SUMMARY_KEYS = [
    "contest",
    "problem",
    "files",
    "schema",
    "rules",
    "output",
    "unknowns",
    "human_decision_values",
    "decision_overrides",
]
ANALYSIS_PAYLOAD_KEYS = [
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
    "code_agent_tasks",
]
FORBIDDEN_FILES = [
    "generated/",
    "runs/",
    ".git/",
    ".venv/",
    "examples/*/contest_overrides.yaml",
]
IMPLEMENTATION_CONSTRAINTS = [
    "OpenAI API runtime 호출 금지",
    "Claude/Anthropic API runtime 호출 금지",
    "기타 외부 LLM API 호출 금지",
    "shell command 자동 실행 기능 추가 금지",
    "subprocess 기반 Code Agent 실행 금지",
    "eval / exec 금지",
    "source 자동 수정 기능 금지",
    "contest_overrides.yaml 자동 수정 금지",
    "ContestSpec 자동 확정 금지",
    "HarnessBlueprint 자동 확정 금지",
    "solver 성능 개선은 task에 명시된 경우가 아니면 금지",
    "멀티에이전트 구조 금지",
    "GitHub Actions 금지",
    "PR 자동화 금지",
    "자동 merge 금지",
    "웹 UI/대시보드 금지",
    "신규 외부 패키지 추가 금지",
    "기존 39개 테스트 회귀 금지",
    "generated/와 runs/는 git에 추가하지 않음",
]
VERIFICATION_COMMANDS = [
    "pytest -q",
    "rm -rf generated runs",
    "python factory/run_factory.py --contest examples/mock_contest_01",
    "python generated/final_harness/run.py",
    "pytest -q",
    "rm -rf generated",
    "python factory/run_factory.py --contest examples/mock_contest_02",
    "python generated/final_harness/run.py",
    "pytest -q",
]
COMPLETION_REPORT_SECTIONS = [
    "추가한 파일",
    "수정한 파일",
    "구현한 작업",
    "변경하지 않은 범위",
    "실행한 검증 명령",
    "pytest 결과",
    "생성 산출물 확인",
    "generated/와 runs/가 커밋 대상이 아닌지 확인",
    "실제 contest_overrides.yaml을 수정하지 않았는지 확인",
    "범위 초과 작업을 하지 않았는지 확인",
]


class CodeAgentPromptError(ValueError):
    """Raised when the code-agent prompt package cannot be safely built."""


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CodeAgentPromptError(f"Required analysis candidates JSON not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CodeAgentPromptError(
            f"Malformed analysis candidates JSON: {exc.msg} at line {exc.lineno} column {exc.colno}."
        ) from exc
    if not isinstance(data, dict):
        raise CodeAgentPromptError("Analysis candidates JSON must be an object.")
    return data


def _read_required_text(path: Path) -> str:
    if not path.exists():
        raise CodeAgentPromptError(f"Required factory artifact not found: {path}")
    return path.read_text(encoding="utf-8")


def _read_contest_spec(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CodeAgentPromptError(f"Required factory artifact not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CodeAgentPromptError(
            f"Malformed contest_spec.json: {exc.msg} at line {exc.lineno} column {exc.colno}."
        ) from exc
    if not isinstance(data, dict):
        raise CodeAgentPromptError("contest_spec.json must be an object.")
    return data


def _compact(value: Any, *, max_string: int = 500, max_items: int = 20) -> Any:
    if isinstance(value, str):
        return value if len(value) <= max_string else value[:max_string] + "\n[TRUNCATED]"
    if isinstance(value, list):
        compacted = [_compact(item, max_string=max_string, max_items=max_items) for item in value[:max_items]]
        if len(value) > max_items:
            compacted.append({"truncated_items": len(value) - max_items})
        return compacted
    if isinstance(value, dict):
        return {
            str(key): _compact(item, max_string=max_string, max_items=max_items)
            for key, item in value.items()
        }
    return value


def summarize_contest_spec(spec: dict[str, Any]) -> dict[str, Any]:
    return {key: _compact(spec.get(key)) for key in SUMMARY_KEYS if key in spec}


def summarize_analysis_candidates(candidates: dict[str, Any]) -> dict[str, Any]:
    payload = candidates.get("payload") if isinstance(candidates.get("payload"), dict) else {}
    summary: dict[str, Any] = {
        "parsed": bool(candidates.get("parsed")),
        "parse_warnings": _compact(candidates.get("parse_warnings", [])),
    }
    for key in ANALYSIS_PAYLOAD_KEYS:
        summary[key] = _compact(payload.get(key, []))
    for key in [
        "accepted_override_candidates",
        "rejected_override_candidates",
        "conflicting_override_candidates",
        "already_confirmed_candidates",
    ]:
        summary[key] = _compact(candidates.get(key, []))
    return summary


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_code_agent_tasks(candidates: dict[str, Any]) -> list[dict[str, Any]]:
    payload = candidates.get("payload") if isinstance(candidates.get("payload"), dict) else {}
    tasks: list[dict[str, Any]] = []
    for index, raw_task in enumerate(_as_list(payload.get("code_agent_tasks")), start=1):
        task = raw_task if isinstance(raw_task, dict) else {"title": str(raw_task)}
        tasks.append({
            "title": str(task.get("title") or f"Task {index}"),
            "priority": str(task.get("priority") or "unknown"),
            "files": [str(item) for item in _as_list(task.get("files"))],
            "acceptance_criteria": [str(item) for item in _as_list(task.get("acceptance_criteria"))],
        })
    return tasks


def _path_parts(path_text: str) -> list[str]:
    normalized = path_text.replace("\\", "/")
    return [part for part in normalized.split("/") if part]


def classify_task_file_path(path_text: str) -> tuple[bool, str | None]:
    if not path_text or not isinstance(path_text, str):
        return False, "empty path"
    if PurePosixPath(path_text).is_absolute() or PureWindowsPath(path_text).is_absolute():
        return False, "absolute path is not allowed"

    parts = _path_parts(path_text)
    lowered = [part.lower() for part in parts]
    if ".." in parts:
        return False, "path traversal is not allowed"
    if not parts:
        return False, "empty path"
    if lowered[0] in {".git", "generated", "runs", ".venv"}:
        return False, "generated, runs, .git, and .venv are not allowed"

    filename = lowered[-1]
    if filename == ".env" or filename.startswith(".env.") or "secret" in filename or "credential" in filename:
        return False, "environment, credential, and secret files are not allowed"
    if any(part in {"secrets", "credentials"} for part in lowered):
        return False, "credential and secret directories are not allowed"
    return True, None


def build_allowed_files(tasks: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, str]]]:
    allowed: list[str] = []
    warnings: list[dict[str, str]] = []
    seen: set[str] = set()
    for task in tasks:
        for path_text in task.get("files", []):
            is_safe, reason = classify_task_file_path(path_text)
            if not is_safe:
                warnings.append({"path": path_text, "reason": reason or "unsafe path"})
                continue
            normalized = path_text.replace("\\", "/")
            if normalized not in seen:
                allowed.append(normalized)
                seen.add(normalized)
    return allowed, warnings


def _markdown_block(text: str, language: str = "text") -> str:
    body = text.rstrip() if text else "- 없음"
    return f"```{language}\n{body}\n```"


def _yaml_block(value: Any) -> str:
    rendered = to_simple_yaml(value)
    return _markdown_block(rendered, "yaml")


def _bullet(items: list[Any], empty: str = "- 없음") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def render_tasks(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "- 구현 작업 후보 없음"
    lines: list[str] = []
    for index, task in enumerate(tasks, start=1):
        files = [
            path_text.replace("\\", "/")
            for path_text in task.get("files", [])
            if classify_task_file_path(path_text)[0]
        ]
        excluded_count = len(task.get("files", [])) - len(files)
        criteria = task.get("acceptance_criteria", [])
        lines.extend([
            f"### {index}. {task.get('title')}",
            "",
            f"- priority: {task.get('priority')}",
            "- files:",
            *([f"  - {item}" for item in files] or ["  - 없음"]),
            f"- excluded unsafe file paths: {excluded_count}",
            "- acceptance criteria:",
            *([f"  - {item}" for item in criteria] or ["  - 없음"]),
            "",
        ])
    return "\n".join(lines).rstrip()


def render_override_status(context: dict[str, Any]) -> str:
    summary = context["analysis_summary"]
    status = {
        "accepted_override_candidates": summary.get("accepted_override_candidates", []),
        "rejected_override_candidates": summary.get("rejected_override_candidates", []),
        "conflicting_override_candidates": summary.get("conflicting_override_candidates", []),
        "already_confirmed_candidates": summary.get("already_confirmed_candidates", []),
    }
    return _yaml_block(status)


def render_human_decisions(context: dict[str, Any]) -> str:
    decisions = {
        "contest_spec_human_decision_values": context["contest_spec_summary"].get("human_decision_values", {}),
        "analysis_human_decisions": context["analysis_summary"].get("human_decisions", []),
        "human_review_summary": context.get("human_review_summary", ""),
    }
    return _yaml_block(decisions)


def default_template() -> str:
    return """# Code Agent Implementation Prompt

## Role
현재 Meta-Harness Factory 구조를 유지하면서 승인된 작업 후보만 구현하는 Code Agent.
불명확한 규칙을 허용된 것으로 가정하지 않는다.
AI 후보는 자동 확정된 결정이 아니다.
사람이 확정하지 않은 override를 실제 설정에 반영하지 않는다.
요청 범위 밖 리팩터링을 하지 않는다.

## Repository
{{REPOSITORY_CONTEXT}}

## Current Project State
{{PROJECT_STATE}}

## Contest Context
{{CONTEST_CONTEXT}}

## Current ContestSpec Summary
{{CONTEST_SPEC_SUMMARY}}

## Gap Report
{{GAP_REPORT}}

## Harness Blueprint
{{HARNESS_BLUEPRINT}}

## AI Analysis Review
{{AI_ANALYSIS_REVIEW}}

## Human Decisions
{{HUMAN_DECISIONS}}

## Override Candidate Status
{{OVERRIDE_STATUS}}

## Implementation Tasks
{{IMPLEMENTATION_TASKS}}

## Files Allowed to Change
{{ALLOWED_FILES}}

## Files That Must Not Be Modified
{{FORBIDDEN_FILES}}

## Implementation Constraints
{{IMPLEMENTATION_CONSTRAINTS}}

## Required Verification
{{VERIFICATION_COMMANDS}}

## Completion Report Format
{{COMPLETION_REPORT_FORMAT}}
"""


def _load_template(template_path: str | Path | None) -> str:
    if template_path is None:
        return default_template()
    path = Path(template_path)
    if not path.exists():
        return default_template()
    text = path.read_text(encoding="utf-8")
    return text if text.strip() else default_template()


def render_prompt(
    context: dict[str, Any],
    *,
    gap_report: str,
    harness_blueprint: str,
    ai_analysis_review: str,
    template_path: str | Path | None,
) -> str:
    verification = list(context["verification_commands"])
    for task in context["code_agent_tasks"]:
        for criterion in task.get("acceptance_criteria", []):
            verification.append(f"Task acceptance: {criterion}")

    replacements = {
        "{{REPOSITORY_CONTEXT}}": "\n".join([
            "- Windows path: `C:\\Dev\\scpc-ai-harness-factory`",
            "- WSL path: `/mnt/c/Dev/scpc-ai-harness-factory`",
        ]),
        "{{PROJECT_STATE}}": "\n".join([
            "- v0.8 이전 흐름: contest folder -> input scan -> ContestSpec -> GapReport -> HarnessBlueprint -> AI analysis prompt -> AI analysis intake -> review pack -> code_agent_task_plan.md",
            "- offline mode: factory는 LLM API를 호출하지 않는다.",
            "- 현재 solver는 baseline 중심이다.",
            "- `generated/`와 `runs/`는 실행 산출물이다.",
            "- 기존 기능을 버리지 않고 확장한다.",
        ]),
        "{{CONTEST_CONTEXT}}": _yaml_block({
            "contest_path": context["contest_path"],
            "source_files": context["source_files"],
            "project_state": context["project_state"],
        }),
        "{{CONTEST_SPEC_SUMMARY}}": _yaml_block(context["contest_spec_summary"]),
        "{{GAP_REPORT}}": _markdown_block(gap_report, "markdown"),
        "{{HARNESS_BLUEPRINT}}": _markdown_block(harness_blueprint, "markdown"),
        "{{AI_ANALYSIS_REVIEW}}": _markdown_block(ai_analysis_review, "markdown"),
        "{{HUMAN_DECISIONS}}": render_human_decisions(context),
        "{{OVERRIDE_STATUS}}": render_override_status(context),
        "{{IMPLEMENTATION_TASKS}}": render_tasks(context["code_agent_tasks"]),
        "{{ALLOWED_FILES}}": _bullet(context["allowed_files"], "- 허용 후보 파일 없음"),
        "{{FORBIDDEN_FILES}}": _bullet(context["files_that_must_not_be_modified"]),
        "{{IMPLEMENTATION_CONSTRAINTS}}": _bullet(context["constraints"]),
        "{{VERIFICATION_COMMANDS}}": _markdown_block("\n".join(verification), "bash"),
        "{{COMPLETION_REPORT_FORMAT}}": "\n".join(
            f"{index}. {section}" for index, section in enumerate(context["completion_report_sections"], start=1)
        ),
    }
    prompt = _load_template(template_path)
    for token, value in replacements.items():
        prompt = prompt.replace(token, value)

    remaining_tokens = sorted(set(re.findall(r"{{[A-Z0-9_]+}}", prompt)))
    if remaining_tokens:
        raise CodeAgentPromptError(f"Unresolved template token(s): {', '.join(remaining_tokens)}")
    return prompt.rstrip() + "\n"


def build_code_agent_work_package(
    *,
    contest_path: str | Path,
    analysis_candidates_path: str | Path,
    output_dir: str | Path = "generated",
    template_path: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    output_root = Path(output_dir)
    analysis_path = Path(analysis_candidates_path)
    contest_spec_path = output_root / "contest_spec.json"
    gap_report_path = output_root / "gap_report.md"
    harness_blueprint_path = output_root / "harness_blueprint.md"
    task_plan_path = output_root / "code_agent_task_plan.md"
    review_path = output_root / "ai_analysis_review.md"

    for filename in REQUIRED_OUTPUT_FILES:
        path = output_root / filename
        if not path.exists():
            raise CodeAgentPromptError(f"Required factory artifact not found: {path}")

    candidates = _read_json_object(analysis_path)
    spec = _read_contest_spec(contest_spec_path)
    gap_report = _read_required_text(gap_report_path)
    harness_blueprint = _read_required_text(harness_blueprint_path)
    _read_required_text(task_plan_path)
    ai_analysis_review = review_path.read_text(encoding="utf-8") if review_path.exists() else ""

    tasks = normalize_code_agent_tasks(candidates)
    allowed_files, unsafe_warnings = build_allowed_files(tasks)
    source_files = {
        "analysis_candidates": str(analysis_path),
        "contest_spec": str(contest_spec_path),
        "gap_report": str(gap_report_path),
        "harness_blueprint": str(harness_blueprint_path),
        "ai_analysis_review": str(review_path) if review_path.exists() else "",
        "code_agent_task_plan": str(task_plan_path),
    }
    context = {
        "version": VERSION,
        "contest_path": str(contest_path),
        "source_files": source_files,
        "project_state": {
            "factory_stage": "code_agent_work_package",
            "offline_only": True,
            "automatic_code_execution": False,
            "automatic_source_modification": False,
            "automatic_shell_command_execution": False,
            "automatic_git_commit": False,
            "automatic_git_push": False,
            "automatic_git_merge": False,
            "llm_api_calls": False,
        },
        "contest_spec_summary": summarize_contest_spec(spec),
        "analysis_summary": summarize_analysis_candidates(candidates),
        "human_review_summary": ai_analysis_review[:1000] + ("\n[TRUNCATED]" if len(ai_analysis_review) > 1000 else ""),
        "code_agent_tasks": tasks,
        "allowed_files": allowed_files,
        "unsafe_task_path_warnings": unsafe_warnings,
        "files_that_must_not_be_modified": FORBIDDEN_FILES,
        "constraints": IMPLEMENTATION_CONSTRAINTS,
        "verification_commands": VERIFICATION_COMMANDS,
        "completion_report_sections": COMPLETION_REPORT_SECTIONS,
    }
    prompt = render_prompt(
        context,
        gap_report=gap_report,
        harness_blueprint=harness_blueprint,
        ai_analysis_review=ai_analysis_review,
        template_path=template_path,
    )
    return context, prompt


def save_code_agent_work_package(
    *,
    contest_path: str | Path,
    analysis_candidates_path: str | Path,
    output_dir: str | Path = "generated",
    template_path: str | Path | None = None,
) -> dict[str, Path]:
    context, prompt = build_code_agent_work_package(
        contest_path=contest_path,
        analysis_candidates_path=analysis_candidates_path,
        output_dir=output_dir,
        template_path=template_path,
    )
    output_root = Path(output_dir)
    return {
        "context_json": write_json(output_root / CONTEXT_FILENAME, context),
        "implementation_prompt": write_text(output_root / PROMPT_FILENAME, prompt),
    }
