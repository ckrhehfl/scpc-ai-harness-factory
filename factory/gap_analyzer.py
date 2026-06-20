from __future__ import annotations

from pathlib import Path
from typing import Any
from factory.utils import write_text


def analyze_gaps(spec: dict[str, Any]) -> dict[str, Any]:
    confirmed: list[str] = []
    gaps: list[str] = []
    risks: list[str] = []
    human_required: list[str] = []
    schema_summary: list[str] = []
    override_applied: list[str] = []

    for item in spec.get("decision_overrides", {}).get("applied", []):
        message = f"{item.get('item')}: override 적용 완료 ({item.get('value')})"
        confirmed.append(message)
        override_applied.append(message)

    files = spec.get("files", {})
    for key in ["train", "test", "sample_submission"]:
        meta = files.get(key, {})
        if meta.get("exists"):
            confirmed.append(
                f"{key}: {meta.get('path')} / rows={meta.get('row_count')} / "
                f"columns={meta.get('column_count', len(meta.get('columns', [])))}"
            )
        else:
            gaps.append(f"{key} 파일이 없다.")

    problem = spec.get("problem", {})
    if problem.get("task_type") == "unknown":
        gaps.append("문제 유형을 아직 확정하지 못했다.")
    else:
        confirmed.append(f"문제 유형 후보: {problem.get('task_type')}")
        for evidence in problem.get("task_type_evidence", []):
            confirmed.append(f"문제 유형 근거: {evidence}")

    output = spec.get("output", {})
    if output.get("required_columns"):
        confirmed.append(f"제출 컬럼: {output.get('required_columns')}")
        confirmed.append(f"id 컬럼 후보: {output.get('id_column')}")
        confirmed.append(f"target 컬럼 후보: {output.get('target_column')}")
        confirmed.append(f"기본 제출값 후보: {output.get('default_value')}")
        for evidence in output.get("inference", {}).get("evidence", []):
            confirmed.append(f"제출 형식 근거: {evidence}")
    else:
        gaps.append("sample_submission 기반 제출 컬럼을 찾지 못했다.")

    schema = spec.get("schema", {})
    schema_summary.extend([
        f"train/test 공통 컬럼: {schema.get('common_columns', [])}",
        f"train/test/sample 공통 컬럼: {schema.get('common_all_files_columns', [])}",
        f"train에만 있는 컬럼: {schema.get('train_only_columns', [])}",
        f"test에만 있는 컬럼: {schema.get('test_only_columns', [])}",
        f"sample_submission에만 있는 컬럼: {schema.get('sample_submission_only_columns', [])}",
    ])
    for key in ["train", "test", "sample_submission"]:
        meta = files.get(key, {})
        if not meta.get("exists"):
            continue
        column_parts = []
        for column in meta.get("column_details", []):
            column_parts.append(
                f"{column.get('name')}#{column.get('index')}:{column.get('inferred_type_from_first_row')}"
            )
        schema_summary.append(f"{key} 컬럼 상세: {', '.join(column_parts) or '없음'}")

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
        "schema_summary": schema_summary,
        "override_applied": override_applied,
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
        section("Override 적용", report.get("override_applied", [])),
        section("불명확한 항목", report.get("gaps", [])),
        section("사람 확인 필요", report.get("human_required", [])),
        section("규칙상 위험한 항목", report.get("risks", [])),
        section("데이터 스키마 요약", report.get("schema_summary", [])),
    ])


def save_gap_report(report: dict[str, Any], output_dir: str | Path) -> Path:
    return write_text(Path(output_dir) / "gap_report.md", render_gap_report(report))
