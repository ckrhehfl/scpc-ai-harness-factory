from __future__ import annotations

from pathlib import Path
from typing import Any
from factory.utils import write_text


def analyze_gaps(spec: dict[str, Any]) -> dict[str, Any]:
    confirmed: list[str] = []
    gaps: list[str] = []
    risks: list[str] = []
    human_required: list[str] = []

    files = spec.get("files", {})
    for key in ["train", "test", "sample_submission"]:
        meta = files.get(key, {})
        if meta.get("exists"):
            confirmed.append(f"{key}: {meta.get('path')} / columns={meta.get('columns')} / rows={meta.get('row_count')}")
        else:
            gaps.append(f"{key} 파일이 없다.")

    problem = spec.get("problem", {})
    if problem.get("task_type") == "unknown":
        gaps.append("문제 유형을 아직 확정하지 못했다.")
    else:
        confirmed.append(f"문제 유형 후보: {problem.get('task_type')}")

    output = spec.get("output", {})
    if output.get("required_columns"):
        confirmed.append(f"제출 컬럼: {output.get('required_columns')}")
    else:
        gaps.append("sample_submission 기반 제출 컬럼을 찾지 못했다.")

    for unknown in spec.get("unknowns", []):
        gaps.append(f"{unknown['item']}: {unknown['why_it_matters']}")
        human_required.append(f"{unknown['item']} 확인 필요")

    rules = spec.get("rules", {})
    if rules.get("leakage_policy") == "strict":
        risks.append("Data leakage 방지 필요: test/eval 정답 추정, 수작업 라벨링, leaderboard 과최적화 금지.")
    for field in ["external_api_allowed", "external_data_allowed", "pretrained_model_allowed", "internet_allowed"]:
        if rules.get(field) == "unknown":
            risks.append(f"{field}가 불명확하므로 기본 실행 경로에 포함하지 말 것.")

    return {
        "confirmed": confirmed,
        "gaps": gaps,
        "risks": risks,
        "human_required": human_required,
    }


def render_gap_report(report: dict[str, Any]) -> str:
    def section(title: str, items: list[str]) -> str:
        if not items:
            return f"## {title}\n\n- 없음\n"
        body = "\n".join(f"- {item}" for item in items)
        return f"## {title}\n\n{body}\n"

    return "\n".join([
        "# Gap Report",
        "",
        section("확인 완료", report.get("confirmed", [])),
        section("빈칸", report.get("gaps", [])),
        section("위험 요소", report.get("risks", [])),
        section("사람 확인 필요", report.get("human_required", [])),
    ])


def save_gap_report(report: dict[str, Any], output_dir: str | Path) -> Path:
    return write_text(Path(output_dir) / "gap_report.md", render_gap_report(report))
