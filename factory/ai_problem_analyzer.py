from __future__ import annotations

from pathlib import Path
from typing import Any

from factory.input_scanner import render_input_scan_report_markdown
from factory.utils import read_text_if_exists, to_simple_yaml, write_text


DEFAULT_TEMPLATE = "templates/prompts/problem_analyzer.md"


def _bullet_list(items: list[Any]) -> str:
    if not items:
        return "- 없음"
    return "\n".join(f"- {item}" for item in items)


def _trim_text(text: str, max_chars: int = 8000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[TRUNCATED]"


def build_documents_section(scan: dict[str, Any]) -> str:
    documents = scan.get("documents", {})
    lines: list[str] = []
    for name in ["description.md", "rules.md", "evaluation.md"]:
        text = documents.get(name, "")
        if not text:
            lines.append(f"## {name}\n\n- not found\n")
            continue
        lines.append(f"## {name}\n\n```markdown\n{_trim_text(text, 5000)}\n```\n")
    return "\n".join(lines)


def build_csv_preview_section(scan: dict[str, Any]) -> str:
    lines: list[str] = []
    for file_info in scan.get("files", []):
        csv_preview = file_info.get("csv_preview")
        if not csv_preview:
            continue
        lines.extend([
            f"## {file_info.get('path')}",
            "",
            f"- role_candidates: {file_info.get('role_candidates', [])}",
            f"- columns: {csv_preview.get('columns')}",
            f"- row_count: {csv_preview.get('row_count')}",
            f"- first_row_preview: {csv_preview.get('first_row_preview')}",
            "",
        ])
    return "\n".join(lines) if lines else "- CSV files not found."


def build_current_artifacts_summary(
    spec: dict[str, Any],
    gap_report: dict[str, Any],
    blueprint: dict[str, Any],
) -> str:
    spec_summary = {
        "problem": spec.get("problem", {}),
        "rules": spec.get("rules", {}),
        "output": spec.get("output", {}),
        "schema": spec.get("schema", {}),
        "unknowns": spec.get("unknowns", []),
        "human_decision_values": spec.get("human_decision_values", {}),
    }
    blueprint_summary = {
        "task_type": blueprint.get("task_type"),
        "recommended_template": blueprint.get("recommended_template"),
        "loader_requirements": blueprint.get("loader_requirements", []),
        "solver_requirements": blueprint.get("solver_requirements", []),
        "verifier_requirements": blueprint.get("verifier_requirements", []),
        "human_decisions_required": blueprint.get("human_decisions_required", []),
        "known_risks": blueprint.get("known_risks", []),
    }
    return "\n".join([
        "## Current ContestSpec Summary",
        "",
        "```yaml",
        to_simple_yaml(spec_summary),
        "```",
        "",
        "## Current GapReport Summary",
        "",
        "### Confirmed",
        _bullet_list(gap_report.get("confirmed", [])),
        "",
        "### Gaps",
        _bullet_list(gap_report.get("gaps", [])),
        "",
        "### Risks",
        _bullet_list(gap_report.get("risks", [])),
        "",
        "## Current HarnessBlueprint Summary",
        "",
        "```yaml",
        to_simple_yaml(blueprint_summary),
        "```",
    ])


def build_problem_analysis_prompt(
    scan: dict[str, Any],
    spec: dict[str, Any],
    gap_report: dict[str, Any],
    blueprint: dict[str, Any],
    *,
    template_path: str | Path = DEFAULT_TEMPLATE,
) -> str:
    template = read_text_if_exists(template_path)
    if not template:
        template = DEFAULT_PROBLEM_ANALYZER_TEMPLATE

    replacements = {
        "{{CONTEST_PATH}}": str(scan.get("contest_path", "unknown")),
        "{{CONTEST_DOCUMENTS}}": build_documents_section(scan),
        "{{INPUT_SCAN_REPORT}}": render_input_scan_report_markdown(scan),
        "{{CSV_PREVIEWS}}": build_csv_preview_section(scan),
        "{{CURRENT_ARTIFACTS_SUMMARY}}": build_current_artifacts_summary(spec, gap_report, blueprint),
    }
    prompt = template
    for token, value in replacements.items():
        prompt = prompt.replace(token, value)
    return prompt


def save_ai_problem_analysis_prompt(
    scan: dict[str, Any],
    spec: dict[str, Any],
    gap_report: dict[str, Any],
    blueprint: dict[str, Any],
    output_dir: str | Path,
    *,
    template_path: str | Path = DEFAULT_TEMPLATE,
) -> Path:
    prompt = build_problem_analysis_prompt(scan, spec, gap_report, blueprint, template_path=template_path)
    return write_text(Path(output_dir) / "ai_problem_analysis_prompt.md", prompt)


DEFAULT_PROBLEM_ANALYZER_TEMPLATE = """# AI Problem Analyzer Prompt

You are analyzing an SCPC AI Challenge contest folder for Meta-Harness Factory v0.6.
Do not produce a final contest submission. Do not write solver code. Your job is to propose design candidates that a human will review.

Contest path: `{{CONTEST_PATH}}`

# Source Documents

{{CONTEST_DOCUMENTS}}

# Input Scan Report

{{INPUT_SCAN_REPORT}}

# CSV Preview

{{CSV_PREVIEWS}}

# Current Factory Artifacts

{{CURRENT_ARTIFACTS_SUMMARY}}

# Required Output

Return a structured analysis with these sections:

1. Problem type candidates
2. Input structure interpretation
3. Output structure interpretation
4. Evaluation metric candidates
5. Rule-risk analysis
6. Candidate judgment for API / external data / internet / pretrained model usage
7. Required harness modules
8. Solver candidates, keeping the current baseline path intact
9. Decisions a human must confirm
10. Candidate ContestSpec updates
11. Candidate HarnessBlueprint updates
12. Code Agent Task Plan

Important constraints:

- Do not assume that unknown rules are allowed.
- Do not add runtime LLM API calls.
- Do not optimize the solver in this step.
- Treat all suggestions as candidates only.
- The human must confirm and encode decisions in contest_overrides.yaml before the factory treats them as final.
"""
